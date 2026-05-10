from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    selecting_country = State()
    selecting_plan = State()
    confirming_order = State()
    awaiting_payment = State()


class SupportFlow(StatesGroup):
    writing_message = State()


class AdminBroadcastFlow(StatesGroup):
    writing_message = State()
    confirming = State()


class AdminMarkupFlow(StatesGroup):
    entering_value = State()


class AdminManualEsimFlow(StatesGroup):
    entering_user = State()
    selecting_plan = State()
    confirming = State()
