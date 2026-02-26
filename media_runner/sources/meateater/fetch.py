from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class FetchResult:
    ok: bool
    text: str = ""
    error: str = ""


def fetch_html(url: str, *, timeout: int = 30, sleep_s: float = 0.0) -> FetchResult:
    """
    Thin wrapper so we can log errors cleanly and throttle if needed.
    """
    try:
        if sleep_s > 0:
            time.sleep(sleep_s)

        r = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "media_runner/1.0 (local script)"},
        )
        r.raise_for_status()
        return FetchResult(ok=True, text=r.text)
    except Exception as e:
        return FetchResult(ok=False, error=str(e))
