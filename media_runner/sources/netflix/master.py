from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import requests
import pandas as pd
from dateutil import parser as dateparser

from .match import normalize_title

WIKI_PAGE_TITLE = "List_of_Netflix_original_stand-up_comedy_specials"
API_URL = "https://en.wikipedia.org/w/api.php"

EXPECTED_COLS = {"Air Date", "Season", "Episode", "Title"}


@dataclass
class WikiRefreshResult:
    ok: bool
    changed: bool = False
    reason: str = ""
    count_before: int = 0
    count_after: int = 0


def fetch_page_html() -> str:
    params = {
        "action": "parse",
        "page": WIKI_PAGE_TITLE,
        "prop": "text",
        "format": "json",
        "formatversion": 2,
    }
    headers = {"User-Agent": "media-runner/1.0 (local script)"}
    r = requests.get(API_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["parse"]["text"]


def pick_specials_table(html: str) -> pd.DataFrame:
    tables = pd.read_html(StringIO(html))
    for df in tables:
        cols = [str(c).strip().lower() for c in df.columns]
        if "title" in cols and "release date" in cols:
            return df
    raise RuntimeError("Could not find Specials table (Title + Release date)")


def parse_air_date(val) -> pd.Timestamp:
    if pd.isna(val):
        return pd.NaT
    txt = str(val).strip()
    if not txt:
        return pd.NaT

    txt = re.sub(r"\[\d+\]", "", txt).strip()
    low = txt.lower()
    if low in {"awaiting release", "tba", "tbd"}:
        return pd.NaT

    try:
        dt = dateparser.parse(txt, fuzzy=True)
        return pd.Timestamp(dt)
    except Exception:
        return pd.NaT


def build_master(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    df = df[["Title", "Release date"]].rename(columns={"Release date": "Air Date"})
    df["Air Date Parsed"] = df["Air Date"].apply(parse_air_date)
    df = df.dropna(subset=["Air Date Parsed"])

    df["Season"] = df["Air Date Parsed"].dt.year.astype(int)
    df = df.sort_values(
        ["Season", "Air Date Parsed", "Title"], kind="stable"
    ).reset_index(drop=True)
    df["Episode"] = df.groupby("Season").cumcount() + 1
    df["Title"] = df["Title"].apply(
        lambda s: normalize_title(str(s)).title()
    )  # pretty-ish titles

    # keep exact columns your loader expects
    return df[["Air Date", "Season", "Episode", "Title"]]


def _yaml_quote(s: str) -> str:
    s = (s or "").replace("'", "''")
    return f"'{s}'"


def build_kometa_yaml(master: pd.DataFrame, plex_show_title: str) -> str:
    seasons: Dict[int, Dict[int, str]] = {}
    for _, row in master.iterrows():
        season = int(row["Season"])
        ep = int(row["Episode"])
        title = str(row["Title"])
        seasons.setdefault(season, {})[ep] = title

    lines: List[str] = []
    lines.append("metadata:")
    lines.append(f"  {_yaml_quote(plex_show_title)}:")
    lines.append("    seasons:")

    for season in sorted(seasons.keys()):
        lines.append(f"      {season}:")
        lines.append("        episodes:")
        for ep in sorted(seasons[season].keys()):
            title = seasons[season][ep]
            lines.append(f"          {ep}:")
            lines.append(f"            title: {_yaml_quote(title)}")

    lines.append("")
    return "\n".join(lines)


def _read_existing_csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return sum(1 for _ in reader)
    except Exception:
        return 0


def refresh_master(
    *,
    master_csv: Path,
    master_json: Optional[Path] = None,
    kometa_metadata_dir: Optional[Path] = None,
    kometa_yml_name: Optional[str] = None,
    plex_show_title: str = "Netflix Stand Up Specials",
) -> WikiRefreshResult:
    """
    Refresh Wikipedia -> master CSV/JSON -> Kometa YAML.

    - Always writes master_csv.
    - Writes master_json if provided.
    - Writes Kometa YAML if kometa_metadata_dir + kometa_yml_name provided.
    """
    before = _read_existing_csv_count(master_csv)

    try:
        html = fetch_page_html()
        specials = pick_specials_table(html)
        master_df = build_master(specials)

        # Ensure output dirs exist
        master_csv.parent.mkdir(parents=True, exist_ok=True)
        master_df.to_csv(master_csv, index=False, encoding="utf-8")

        if master_json is not None:
            master_json.parent.mkdir(parents=True, exist_ok=True)
            records = master_df.to_dict(orient="records")
            master_json.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        if kometa_metadata_dir and kometa_yml_name:
            kometa_metadata_dir.mkdir(parents=True, exist_ok=True)
            yml_text = build_kometa_yaml(master_df, plex_show_title=plex_show_title)
            target = kometa_metadata_dir / kometa_yml_name
            target.write_text(yml_text, encoding="utf-8")

        after = len(master_df)
        changed = after != before
        return WikiRefreshResult(
            ok=True, changed=changed, count_before=before, count_after=after
        )

    except Exception as e:
        return WikiRefreshResult(
            ok=False,
            changed=False,
            reason=str(e),
            count_before=before,
            count_after=before,
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
