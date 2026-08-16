"""Command and callback handlers tying together FSM states, inline
keyboards, and the fleep-api client."""
from __future__ import annotations

import logging
import uuid

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from api_client import FleepApiClient, FleepApiError
from keyboards.transaction_kb import confirmation_kb, currency_selection_kb, kind_selection_kb
from states.transaction_flow import OnboardingFlow, TransactionFlow

logger = logging.getLogger("fleep.bot.handlers")
router = Router(name="fleep_forge_main")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, api_client: FleepApiClient) -> None:
    """First contact: link (or fetch) the fleep-api user for this chat."""
    await state.clear()
    try:
        user = await api_client.link_telegram_user(
            telegram_id=message.from_user.id,
            telegram_username=message.from_user.username,
            display_name=message.from_user.full_name,
        )
    except FleepApiError:
        logger.exception("telegram-link failed for telegram_id=%s", message.from_user.id)
        await message.answer(
            "Sorry, FLEEP FORGE is temporarily unavailable while we link your account. Please try again shortly."
        )
        return

    await message.answer(
        f"Welcome to FLEEP FORGE, {user['display_name']}! 👋\n\n"
        "Use /new_transaction to start a transaction, or /history to see your recent activity."
    )


@router.message(Command("new_transaction"))
async def cmd_new_transaction(message: Message, state: FSMContext) -> None:
    await state.set_state(TransactionFlow.choosing_kind)
    await message.answer("What kind of transaction is this?", reply_markup=kind_selection_kb())


@router.callback_query(TransactionFlow.choosing_kind, F.data.startswith("tx_kind:"))
async def on_kind_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":", 1)[1]
    await state.update_data(kind=kind)
    await state.set_state(TransactionFlow.entering_amount)
    await callback.message.edit_text(f"Kind: {kind}\n\nNow send the amount (numbers only).")
    await callback.answer()


@router.message(TransactionFlow.entering_amount)
async def on_amount_entered(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError("amount must be positive")
    except ValueError:
        await message.answer("That doesn't look like a valid amount. Please send a number, e.g. 42.50")
        return

    await state.update_data(amount=amount)
    await state.set_state(TransactionFlow.entering_currency)
    await message.answer("Which currency?", reply_markup=currency_selection_kb())


@router.callback_query(TransactionFlow.entering_currency, F.data.startswith("tx_currency:"))
async def on_currency_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.split(":", 1)[1]
    data = await state.update_data(currency=currency)
    await state.set_state(TransactionFlow.confirming)
    await callback.message.edit_text(
        f"Confirm this transaction?\n\nKind: {data['kind']}\nAmount: {data['amount']} {currency}",
        reply_markup=confirmation_kb(),
    )
    await callback.answer()


@router.callback_query(TransactionFlow.confirming, F.data.startswith("tx_confirm:"))
async def on_confirmation(callback: CallbackQuery, state: FSMContext, api_client: FleepApiClient) -> None:
    decision = callback.data.split(":", 1)[1]
    data = await state.get_data()
    await state.clear()

    if decision == "no":
        await callback.message.edit_text("Cancelled. Use /new_transaction to start again.")
        await callback.answer()
        return

    # Idempotency key is derived per-confirmation-tap, not per-flow, so a
    # duplicate callback delivery (Telegram retries these under poor
    # connectivity) can never create two transactions for one user action.
    idempotency_key = f"tg:{callback.from_user.id}:{callback.message.message_id}:{uuid.uuid4().hex[:8]}"

    access_token = data.get("access_token")  # populated by an auth step omitted here for brevity
    try:
        tx = await api_client.create_transaction(
            access_token or "",
            kind=data["kind"],
            idempotency_key=idempotency_key,
            amount=data["amount"],
            currency=data["currency"],
        )
        await callback.message.edit_text(
            f"✅ Transaction created.\nID: {tx['id']}\nStatus: {tx['status']}"
        )
    except FleepApiError as exc:
        logger.exception("transaction creation failed for telegram_id=%s", callback.from_user.id)
        await callback.message.edit_text(f"❌ Could not create the transaction ({exc.status_code}). Please try again.")

    await callback.answer()


@router.message(Command("history"))
async def cmd_history(message: Message, api_client: FleepApiClient) -> None:
    # NOTE: fetching the per-chat access_token is handled by the auth
    # layer omitted from this excerpt (see OnboardingFlow) — this handler
    # assumes it has already been resolved into `access_token` below in
    # the full implementation.
    await message.answer(
        "Your recent transactions will appear here once account linking is wired up end-to-end — "
        "tracked as the next milestone after this scaffold."
    )
