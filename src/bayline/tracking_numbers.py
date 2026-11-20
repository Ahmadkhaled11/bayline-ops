"""Bayline tracking numbers use a Luhn check digit."""

import re


def normalise(text: str) -> str:
    return re.sub(r"[\s-]", "", text).upper()


def _sum(digits: str) -> int:
    total = 0
    for index, digit in enumerate(reversed(digits)):
        value = int(digit) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total


def make_tracking_number(serial: int) -> str:
    if not isinstance(serial, int) or not 0 <= serial <= 999999:
        raise ValueError("Serial must be between 0 and 999999")
    digits = f"26{serial:06}"
    return f"BYL{digits}{(-_sum(digits + '0')) % 10}"


def is_valid(text: str) -> bool:
    return bool(re.fullmatch(r"BYL26[0-9]{7}", text)) and _sum(text[3:]) % 10 == 0
