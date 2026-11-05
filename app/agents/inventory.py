from decimal import Decimal


def available_units(on_hand: int, reserved: int, incoming: int = 0) -> int:
    return max(0, on_hand - reserved + incoming)


def reorder_flag(on_hand: int, reorder_point: int) -> bool:
    return on_hand <= reorder_point


def money_inr_to_paise(amount: Decimal) -> int:
    return int(amount * 100)
