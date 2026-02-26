from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Episode:
    code: str  # "S02E03"
    season: int
    episode: int
    title: str
    summary: str = ""
    date_iso: Optional[str] = None
    youtube: Optional[str] = None
    source_url: Optional[str] = None
