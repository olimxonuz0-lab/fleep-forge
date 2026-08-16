import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.transaction import Transaction, TransactionStatus
from transactions.state_machine import (
    InvalidTransitionError,
    TransactionEngine,
)


async def _reload_with_events(db_session, transaction_id) -> Transaction:
    """Async-safe way to read a transaction's events.

    Touching `Transaction.events` after a plain lazy-loaded fetch raises
    MissingGreenlet under the async engine (the same class of bug fixed in
    TransactionEngine._record_event) — tests must eager-load explicitly.
    """
    result = await db_session.execute(
        select(Transaction).where(Transaction.id == transaction_id).options(selectinload(Transaction.events))
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_create_transaction_starts_pending(db_session, test_user):
    engine = TransactionEngine(db_session)
    tx = await engine.create(
        user_id=test_user.id,
        kind="deposit",
        idempotency_key=str(uuid.uuid4()),
        amount=10.0,
        currency="USD",
    )
    await db_session.commit()
    tx = await _reload_with_events(db_session, tx.id)

    assert tx.status == TransactionStatus.PENDING
    assert len(tx.events) == 1
    assert tx.events[0].to_status == TransactionStatus.PENDING.value


@pytest.mark.asyncio
async def test_create_is_idempotent(db_session, test_user):
    engine = TransactionEngine(db_session)
    key = str(uuid.uuid4())

    tx1 = await engine.create(user_id=test_user.id, kind="deposit", idempotency_key=key)
    await db_session.commit()
    tx2 = await engine.create(user_id=test_user.id, kind="deposit", idempotency_key=key)
    await db_session.commit()

    assert tx1.id == tx2.id


@pytest.mark.asyncio
async def test_valid_transition_sequence(db_session, test_user):
    engine = TransactionEngine(db_session)
    tx = await engine.create(user_id=test_user.id, kind="deposit", idempotency_key=str(uuid.uuid4()))
    await db_session.commit()

    await engine.transition(tx, TransactionStatus.PROCESSING)
    await engine.transition(tx, TransactionStatus.COMPLETED)
    await db_session.commit()
    tx = await _reload_with_events(db_session, tx.id)

    assert tx.status == TransactionStatus.COMPLETED
    assert [e.to_status for e in tx.events] == ["pending", "processing", "completed"]


@pytest.mark.asyncio
async def test_invalid_transition_raises(db_session, test_user):
    engine = TransactionEngine(db_session)
    tx = await engine.create(user_id=test_user.id, kind="deposit", idempotency_key=str(uuid.uuid4()))
    await db_session.commit()

    with pytest.raises(InvalidTransitionError):
        await engine.transition(tx, TransactionStatus.COMPLETED)  # PENDING -> COMPLETED is not allowed


@pytest.mark.asyncio
async def test_run_success_path_completes(db_session, test_user):
    engine = TransactionEngine(db_session)
    tx = await engine.create(user_id=test_user.id, kind="payout", idempotency_key=str(uuid.uuid4()))
    await db_session.commit()

    async def handler(t: Transaction) -> None:
        t.payload["processed"] = True

    await engine.run(tx, handler)
    await db_session.commit()

    assert tx.status == TransactionStatus.COMPLETED
    assert tx.payload["processed"] is True


@pytest.mark.asyncio
async def test_run_failure_triggers_compensation(db_session, test_user):
    engine = TransactionEngine(db_session)
    tx = await engine.create(user_id=test_user.id, kind="payout", idempotency_key=str(uuid.uuid4()))
    await db_session.commit()

    compensated = {"called": False}

    async def failing_handler(t: Transaction) -> None:
        raise RuntimeError("upstream payment provider timed out")

    async def compensator(t: Transaction, reason: str) -> None:
        compensated["called"] = True
        t.payload["compensation_reason"] = reason

    await engine.run(tx, failing_handler, compensator=compensator)
    await db_session.commit()

    assert compensated["called"] is True
    assert tx.status == TransactionStatus.COMPENSATED
    assert "timed out" in tx.payload["compensation_reason"]


@pytest.mark.asyncio
async def test_run_failure_without_compensator_stays_failed(db_session, test_user):
    engine = TransactionEngine(db_session)
    tx = await engine.create(user_id=test_user.id, kind="payout", idempotency_key=str(uuid.uuid4()))
    await db_session.commit()

    async def failing_handler(t: Transaction) -> None:
        raise ValueError("insufficient funds")

    await engine.run(tx, failing_handler)
    await db_session.commit()

    assert tx.status == TransactionStatus.FAILED
    assert tx.failure_reason == "insufficient funds"
