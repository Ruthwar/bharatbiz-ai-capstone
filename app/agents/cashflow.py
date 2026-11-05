def projected_cash(cash_paise: int, inflows_paise: int, outflows_paise: int, minimum_buffer_paise: int) -> dict:
    ending = cash_paise + inflows_paise - outflows_paise
    return {"ending_cash_paise": ending, "buffer_paise": minimum_buffer_paise,
            "feasible": ending >= minimum_buffer_paise}
