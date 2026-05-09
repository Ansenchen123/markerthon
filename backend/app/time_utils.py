from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


TAIPEI_TZ = ZoneInfo("Asia/Taipei")
RETURN_PERIOD = timedelta(days=3)


def now_taipei() -> datetime:
    """Return a naive Asia/Taipei timestamp for consistent SQLite storage."""
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)


def due_at_from(issued_at: datetime) -> datetime:
    return issued_at + RETURN_PERIOD
