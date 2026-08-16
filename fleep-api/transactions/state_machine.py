"""
Transaction state machine.

This module is the transactional core referenced throughout the project
proposal. It enforces valid state transitions, guarantees idempotency for
retried calls (critical for Telegram webhook delivery, which can and does
redeliver updates), and provides a compensation hook for rollback of
multi-step operations.

Design notes:
- Transitions are defined explicitly as a directed graph (ALLOWED_TRANSITIONS)
  rather than scattered `if` checks, so the full state space is auditable
  in one place.
- Every transition is written to TransactionEvent before the Transaction
  row is updated, so a crash between the two leaves an event log that a
  reconciliation job can replay against.
- `execute` is the only supported way to run a transaction's business
  logic; callers are not expected to mutate Transaction.status directly.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.transaction import Transaction, TransactionEvent, TransactionStatus

logger = logging.getLogger("fleep.transactions")

Handler = Callable[[Transaction], Awaitable[None]]
Compensator = Callable[[Transaction, str], Awaitable[None]]

ALLOWED_TRANSITIONS: dict[TransactionStatus, set[TransactionStatus]] = {
    TransactionStatus.PENDING: {TransactionStatus.PROCESSING, TransactionStatus.CANCELLED},
    TransactionStatus.PROCESSING: {
        TransactionStatus.AWAITING_CONFIRMATION,
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
    },
    TransactionStatus.AWAITING_CONFIRMATION: {
        TransactionStatus.PROCESSING,
        TransactionStatus.CANCELLED,
        TransactionStatus.FAILED,
    },
    TransactionStatus.FAILED: {TransactionStatus.COMPENSATING, TransactionStatus.CANCELLED},
    TransactionStatus.COMPENSATING: {TransactionStatus.COMPENSATED, TransactionStatus.FAILED},
    TransactionStatus.COMPLETED: set(),
    TransactionStatus.COMPENSATED: set(),
    TransactionStatus.CANCELLED: set(),
}


class InvalidTransitionError(Exception):
    def __init__(self, from_status: TransactionStatus, to_status: TransactionStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition transaction from {from_status.value} to {to_status.value}")


class TransactionNotFoundError(Exception):
    pass


class TransactionEngine:
    """Stateful facade over a DB session for running transaction transitions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id,
        kind: str,
        idempotency_key: str,
        amount: Optional[float] = None,
        currency: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> Transaction:
        """Create a new transaction, or return the existing one if this
        idempotency key was already used. This is what makes retried
        Telegram webhook deliveries and double-tapped UI buttons safe.
        """
        existing = await self.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info("idempotent replay for key=%s -> tx=%s", idempotency_key, existing.id)
            return existing

        tx = Transaction(
            user_id=user_id,
            kind=kind,
            idempotency_key=idempotency_key,
            amount=amount,
            currency=currency,
            payload=payload or {},
            status=TransactionStatus.PENDING,
        )
        self.session.add(tx)
        await self.session.flush()

        await self._record_event(tx, from_status=None, to_status=TransactionStatus.PENDING, reason="created")
        return tx

    async def transition(
        self,
        transaction: Transaction,
        to_status: TransactionStatus,
        *,
        reason: Optional[str] = None,
        actor: str = "system",
        metadata: Optional[dict] = None,
    ) -> Transaction:
        current = transaction.status
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if to_status not in allowed:
            raise InvalidTransitionError(current, to_status)

        await self._record_event(
            transaction, from_status=current, to_status=to_status, reason=reason, actor=actor, metadata=metadata
        )
        transaction.status = to_status
        if to_status == TransactionStatus.FAILED and reason:
            transaction.failure_reason = reason

        await self.session.flush()
        return transaction

    async def run(
        self,
        transaction: Transaction,
        handler: Handler,
        *,
        compensator: Optional[Compensator] = None,
    ) -> Transaction:
        """Execute `handler` for a PENDING transaction, moving it through
        PROCESSING -> COMPLETED, or into FAILED (and optionally
        COMPENSATING) if `handler` raises.
        """
        await self.transition(transaction, TransactionStatus.PROCESSING, reason="handler started")

        try:
            await handler(transaction)
        except Exception as exc:  # noqa: BLE001 - intentionally broad: any handler failure must be caught
            logger.exception("transaction %s handler failed", transaction.id)
            await self.transition(
                transaction, TransactionStatus.FAILED, reason=str(exc), actor="system"
            )
            if compensator is not None:
                await self.transition(
                    transaction, TransactionStatus.COMPENSATING, reason="running compensator"
                )
                try:
                    await compensator(transaction, str(exc))
                    await self.transition(
                        transaction, TransactionStatus.COMPENSATED, reason="compensator succeeded"
                    )
                except Exception as comp_exc:  # noqa: BLE001
                    logger.exception("compensator for transaction %s also failed", transaction.id)
                    # Stay in COMPENSATING — this requires manual/ops intervention.
                    transaction.failure_reason = f"compensation failed: {comp_exc}"
                    await self.session.flush()
            return transaction

        await self.transition(transaction, TransactionStatus.COMPLETED, reason="handler succeeded")
        return transaction

    async def _record_event(
        self,
        transaction: Transaction,
        *,
        from_status: Optional[TransactionStatus],
        to_status: TransactionStatus,
        reason: Optional[str] = None,
        actor: str = "system",
        metadata: Optional[dict] = None,
    ) -> TransactionEvent:
        # `transaction.id` is always populated by this point: `create()`
        # flushes the new Transaction row before its first call to
        # _record_event, and every other call site operates on an
        # already-persisted transaction. We set the FK explicitly and add
        # the event directly to the session rather than appending to the
        # `transaction.events` relationship — appending to a
        # not-yet-loaded collection triggers an implicit lazy-load, which
        # raises MissingGreenlet under the async engine. This was caught
        # by test_create_transaction_starts_pending; see
        # tests/test_state_machine.py.
        event = TransactionEvent(
            transaction_id=transaction.id,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            reason=reason,
            actor=actor,
            metadata_=metadata or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event
