from __future__ import annotations

import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict

from .match import normalize_title

EXPECTED_COLS = {"Air Date", "Season", "Episode", "Title"}


@dataclass
class WikiRefreshResult:
    ok: bool
    stdout_tail: str = ""
    stderr_tail: str = ""


def run_wiki_scraper(
    wiki_scraper_path: Path, python_exe: str | None = None
) -> WikiRefreshResult:
    if not wiki_scraper_path.exists():
        return WikiRefreshResult(ok=False, stderr_tail="wiki_scraper.py missing")

    py = python_exe or sys.executable
    r = subprocess.run([py, str(wiki_scraper_path)], capture_output=True, text=True)

    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()

    out_tail = "\n".join(out.splitlines()[-20:]) if out else ""
    err_tail = "\n".join(err.splitlines()[-20:]) if err else ""

    return WikiRefreshResult(
        ok=(r.returncode == 0), stdout_tail=out_tail, stderr_tail=err_tail
    )


def load_master_csv(master_csv: Path) -> List[Dict]:
    if not master_csv.exists():
        raise FileNotFoundError(f"Master CSV not found: {master_csv}")

    rows: List[Dict] = []
    with master_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not EXPECTED_COLS.issubset(set(reader.fieldnames or [])):
            raise ValueError(
                f"Master CSV missing columns. Need: {sorted(EXPECTED_COLS)}; got: {reader.fieldnames}"
            )

        for r in reader:
            try:
                season = int(r["Season"])
                episode = int(r["Episode"])
            except Exception:
                continue

            title = str(r["Title"]).strip()
            if not title:
                continue

            rows.append(
                {
                    "season": season,
                    "episode": episode,
                    "title": title,
                    "title_cmp": normalize_title(title),
                }
            )

    if not rows:
        raise ValueError("Master CSV contained zero usable rows.")
    return rows
