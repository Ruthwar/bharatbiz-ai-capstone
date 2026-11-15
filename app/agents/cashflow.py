from datetime import date, timedelta
from decimal import Decimal

from app.scenarios.contracts import ReceiptOverlay
from app.schemas.contracts import BusinessState, CashDay, CashProjection

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


def project_dated_cash(
    opening_cash_rupees: Decimal,
    minimum_buffer_rupees: Decimal,
    outflow_rupees: Decimal,
    receipts: tuple[ReceiptOverlay, ...],
    start_date: date,
    planning_horizon: date,
    receipt_timing: str = "actual",
) -> CashProjection:
    if outflow_rupees < 0:
        raise ValueError("Outflows must be non-negative magnitudes")
    if receipt_timing not in {"actual", "on_time"}:
        raise ValueError("Receipt timing must be actual or on_time")
    end_date = max(start_date, planning_horizon)
    closing = opening_cash_rupees
    schedule = []
    current = start_date
    while current <= end_date:
        inflow = sum(
            (
                receipt.amount_rupees
                for receipt in receipts
                if (receipt.actual_date if receipt_timing == "actual" else receipt.expected_date) == current
            ),
            ZERO_RUPEES,
        )
        outflow = outflow_rupees if current == start_date else ZERO_RUPEES
        closing = closing + inflow - outflow
        headroom = closing - minimum_buffer_rupees
        schedule.append(
            CashDay(
                date=current,
                receipts_rupees=inflow,
                procurement_outflow_rupees=outflow,
                closing_cash_rupees=closing,
                headroom_rupees=headroom,
                feasible=headroom >= 0,
            )
        )
        current += timedelta(days=1)
    return CashProjection(
        ending_cash_rupees=closing,
        minimum_buffer_rupees=minimum_buffer_rupees,
        headroom_rupees=closing - minimum_buffer_rupees,
        feasible=all(day.feasible for day in schedule),
        daily_schedule=schedule,
    )
