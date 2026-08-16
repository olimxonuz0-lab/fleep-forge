import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.deps import get_current_user
from models.transaction import Transaction
from models.user import User
from schemas.transaction import (
    TransactionCreate,
    TransactionDetail,
    TransactionRead,
    TransactionTransitionRequest,
)
from transactions.state_machine import (
    InvalidTransitionError,
    TransactionEngine,
)

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


async def _get_owned_transaction(
    transaction_id: uuid.UUID, user: User, db: AsyncSession, with_events: bool = False
) -> Transaction:
    stmt = select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user.id)
    if with_events:
        stmt = stmt.options(selectinload(Transaction.events))
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return tx


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    engine = TransactionEngine(db)
    tx = await engine.create(
        user_id=user.id,
        kind=payload.kind,
        idempotency_key=payload.idempotency_key,
        amount=payload.amount,
        currency=payload.currency,
        payload=payload.payload,
    )
    await db.commit()
    await db.refresh(tx)
    return tx


@router.get("", response_model=list[TransactionRead])
async def list_transactions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[Transaction]:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get("/{transaction_id}", response_model=TransactionDetail)
async def get_transaction(
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    return await _get_owned_transaction(transaction_id, user, db, with_events=True)


@router.post("/{transaction_id}/transition", response_model=TransactionDetail)
async def transition_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionTransitionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    tx = await _get_owned_transaction(transaction_id, user, db, with_events=True)
    engine = TransactionEngine(db)
    try:
        await engine.transition(
            tx, payload.to_status, reason=payload.reason, actor=f"user:{user.id}"
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(tx)
    return tx
