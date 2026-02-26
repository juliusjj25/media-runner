from __future__ import annotations

from datetime import datetime, time, timedelta
import os

try:
    from zoneinfo import ZoneInfo
except Exception:  # py39 should have it, but just in case
    ZoneInfo = None  # type: ignore


def _local_tz():
    # Windows: rely on system local timezone; ZoneInfo(None) isn't a thing
    # We'll just use naive local time consistently for windowing.
    return None


def window_start_local(anchor_hour: int = 8) -> datetime:
    """
    Returns the start of the current window anchored at anchor_hour (default 8AM local).
    Window is [start, start+24h).
    """
    now = datetime.now()
    anchor = now.replace(hour=anchor_hour, minute=0, second=0, microsecond=0)
    if now < anchor:
        anchor = anchor - timedelta(days=1)
    return anchor


def window_key(anchor_hour: int = 8) -> str:
    """Key used for filenames, based on window start date."""
    ws = window_start_local(anchor_hour=anchor_hour)
    return ws.strftime("%Y-%m-%d")
