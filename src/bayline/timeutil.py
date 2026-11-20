"""UTC storage and local calendar dates."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("A time zone is required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Expected an ISO 8601 time with a time zone") from exc


def to_utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A time zone is required")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_date(value: datetime, tz: str) -> date:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A time zone is required")
    return value.astimezone(ZoneInfo(tz)).date()


def format_day(value: date) -> str:
    days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    months = ("January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December")
    return f"{days[value.weekday()]} {value.day} {months[value.month - 1]} {value.year}"
