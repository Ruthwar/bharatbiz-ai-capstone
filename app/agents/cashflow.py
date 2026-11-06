from decimal import Decimal

from app.schemas.contracts import BusinessState, CashProjection

ZERO_RUPEES = Decimal("0.00")


def projected_cash(
    cash_rupees: Decimal,
    inflows_rupees: Decimal,
    outflows_rupees: Decimal,
    minimum_buffer_rupees: Decimal,
) -> dict:
    if inflows_rupees < 0 or outflows_rupees < 0:
        raise ValueError("Inflows and outflows must be non-negative magnitudes")
    ending = cash_rupees + inflows_rupees - outflows_rupees
    return {
        "ending_cash_rupees": ending,
        "buffer_rupees": minimum_buffer_rupees,
        "feasible": ending >= minimum_buffer_rupees,
    }


def project_cash(state: BusinessState, outflow_rupees: Decimal = ZERO_RUPEES) -> CashProjection:
    result = projected_cash(
        state.cash_balance_rupees,
        ZERO_RUPEES,
        outflow_rupees,
        state.minimum_cash_buffer_rupees,
    )
    return CashProjection(
        ending_cash_rupees=result["ending_cash_rupees"],
        minimum_buffer_rupees=state.minimum_cash_buffer_rupees,
        headroom_rupees=result["ending_cash_rupees"] - state.minimum_cash_buffer_rupees,
        feasible=result["feasible"],
    )
