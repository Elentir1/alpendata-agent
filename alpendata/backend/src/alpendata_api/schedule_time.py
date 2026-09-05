"""Civil-time recurrences: gaps are skipped, repeated hours run only on their first fold."""

from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from .schemas import Input


class Cadence(Input):
    frequency: Literal["daily", "weekdays", "weekly"]
    local_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    timezone: str = Field(min_length=1, max_length=100)
    weekday: int = Field(default=0, ge=0, le=6)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone") from None
        return value


def next_occurrence(cadence, after):
    zone = ZoneInfo(cadence.timezone)
    first_date = datetime.fromtimestamp(after, zone).date()
    hour, minute = map(int, cadence.local_time.split(":"))
    for offset in range(16):
        day = first_date + timedelta(days=offset)
        if cadence.frequency == "weekdays" and day.weekday() >= 5:
            continue
        if cadence.frequency == "weekly" and day.weekday() != cadence.weekday:
            continue
        local = datetime.combine(day, time(hour, minute), tzinfo=zone)
        stamp = int(local.timestamp())
        # A round trip rejects nonexistent wall times at the spring transition.
        if stamp > after and datetime.fromtimestamp(stamp, zone).replace(tzinfo=None) == local.replace(
            tzinfo=None
        ):
            return stamp
    raise ValueError("No valid occurrence in the next two weeks")
