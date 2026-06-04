from datetime import datetime
from typing import Union
from zoneinfo import ZoneInfo

from babel.dates import format_date
from loguru import logger
from pydantic import BaseModel


def convert_timezone_datetime(
    date_time: datetime, to_tz: Union[str, ZoneInfo], from_tz: Union[str, ZoneInfo] = "Europe/Moscow"
) -> datetime:
    """
    Converts datetime from one timezone to another.

    The function takes a datetime object, assigns the source timezone,
    and converts to the target timezone.

    Args:
        date_time: Datetime object to convert (without timezone info)
        to_tz: Target timezone (IANA string or ZoneInfo object)
        from_tz: Source timezone (default: Moscow timezone)

    Returns:
        datetime: Datetime object in the target timezone
    """
    if isinstance(from_tz, str):
        from_tz = ZoneInfo(from_tz)

    if isinstance(to_tz, str):
        to_tz = ZoneInfo(to_tz)

    datetime_with_tz = date_time.replace(tzinfo=from_tz)
    datetime_converted = datetime_with_tz.astimezone(to_tz)

    return datetime_converted
