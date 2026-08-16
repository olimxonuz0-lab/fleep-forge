from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

TRANSACTION_KINDS = ["deposit", "withdrawal", "transfer"]
SUPPORTED_CURRENCIES = ["USD", "EUR", "UZS"]


def kind_selection_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for kind in TRANSACTION_KINDS:
        builder.button(text=kind.capitalize(), callback_data=f"tx_kind:{kind}")
    builder.adjust(len(TRANSACTION_KINDS))
    return builder.as_markup()


def currency_selection_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for currency in SUPPORTED_CURRENCIES:
        builder.button(text=currency, callback_data=f"tx_currency:{currency}")
    builder.adjust(len(SUPPORTED_CURRENCIES))
    return builder.as_markup()


def confirmation_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data="tx_confirm:yes"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="tx_confirm:no"),
            ]
        ]
    )
