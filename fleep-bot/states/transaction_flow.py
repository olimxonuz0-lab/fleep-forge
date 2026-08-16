"""FSM state groups for aiogram 3's built-in finite state machine."""
from aiogram.fsm.state import State, StatesGroup


class TransactionFlow(StatesGroup):
    """Guides a user through creating a new transaction from a chat."""
    choosing_kind = State()
    entering_amount = State()
    entering_currency = State()
    confirming = State()


class OnboardingFlow(StatesGroup):
    """First-contact flow that links the Telegram identity to a fleep-api
    user before any transactional commands are available."""
    awaiting_display_name = State()
