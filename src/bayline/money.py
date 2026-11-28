"""Money enters as decimal EGP and is stored as whole piastres."""

from decimal import Decimal, InvalidOperation


def egp_to_piastres(value: str | int | Decimal) -> int:
    try:
        amount = Decimal(str(value)) * 100
        if not amount.is_finite() or amount != amount.to_integral_value():
            raise ValueError("Use at most two decimal places")
        return int(amount)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid EGP amount") from exc


def format_egp(piastres: int) -> str:
    return f"{piastres / 100:,.2f} EGP"
