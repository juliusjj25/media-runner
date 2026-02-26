from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any

import yaml

from .models import Episode
from .parse import clean_summary


@dataclass
class MergeResult:
    merged: Dict[str, Dict[str, Any]]
    new_codes: List[str]
    extra_show_meta: Dict[str, Any]


def _yaml_escape(s: str) -> str:
    return (s or "").replace('"', '\\"')


def merge_with_existing(
    yml_path: Path, show_name: str, episodes: Dict[str, Dict[str, Any]]
) -> MergeResult:
    extra_show_meta: Dict[str, Any] = {}
    new_codes: List[str] = []

    if not yml_path.exists():
        return MergeResult(
            merged=episodes, new_codes=sorted(episodes.keys()), extra_show_meta={}
        )

    try:
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise RuntimeError(f"Failed to parse existing YAML: {yml_path} :: {e}")

    if not isinstance(data, dict) or "metadata" not in data:
        return MergeResult(
            merged=episodes, new_codes=sorted(episodes.keys()), extra_show_meta={}
        )

    meta = data.get("metadata", {}) or {}
    show_key = (
        show_name
        if show_name in meta
        else (next(iter(meta.keys())) if meta else show_name)
    )
    show_block = meta.get(show_key, {}) or {}

    # keep extra fields like url_poster
    for k, v in show_block.items():
        if k in ("title", "year", "episodes"):
            continue
        extra_show_meta[k] = v

    existing_eps = show_block.get("episodes", {}) or {}
    if not isinstance(existing_eps, dict):
        return MergeResult(
            merged=episodes,
            new_codes=sorted(episodes.keys()),
            extra_show_meta=extra_show_meta,
        )

    previously_present = set(existing_eps.keys())
    new_codes = sorted(
        code for code in episodes.keys() if code not in previously_present
    )

    # carry forward old episodes not in fresh scrape
    for code, edata in existing_eps.items():
        if code in episodes or not isinstance(edata, dict):
            continue

        summary = clean_summary(str(edata.get("summary", "") or ""))
        episodes[code] = {
            "season": int(edata.get("season", 0) or 0),
            "episode": int(edata.get("episode", 0) or 0),
            "title": str(edata.get("title", "") or ""),
            "date_iso": edata.get("originallyAvailableAt"),
            "summary": summary,
            "youtube": None,
        }

    return MergeResult(
        merged=episodes, new_codes=new_codes, extra_show_meta=extra_show_meta
    )


def write_show_yaml(
    yml_path: Path,
    *,
    show_name: str,
    year: int,
    episodes_by_code: Dict[str, Dict[str, Any]],
    extra_show_meta: Dict[str, Any] | None = None,
) -> None:
    extra_show_meta = extra_show_meta or {}

    # sort for stable output
    rows: List[Tuple[int, int, str, Dict[str, Any]]] = []
    for code, e in episodes_by_code.items():
        rows.append((int(e["season"]), int(e["episode"]), code, e))
    rows.sort(key=lambda x: (x[0], x[1], x[2]))

    lines: List[str] = []
    lines.append("metadata:")
    lines.append(f'  "{_yaml_escape(show_name)}":')
    lines.append(f'    title: "{_yaml_escape(show_name)}"')
    lines.append(f"    year: {int(year)}")

    for k, v in extra_show_meta.items():
        if isinstance(v, str):
            lines.append(f'    {k}: "{_yaml_escape(v)}"')
        elif isinstance(v, (int, float)):
            lines.append(f"    {k}: {v}")
        elif isinstance(v, bool):
            lines.append(f"    {k}: {'true' if v else 'false'}")

    lines.append("    episodes:")

    for season, episode, code, e in rows:
        title = str(e.get("title", "") or "")
        date_iso = e.get("date_iso")
        summary = str(e.get("summary", "") or "")
        lines.append(f'      "{code}":')
        lines.append(f'        title: "{_yaml_escape(title)}"')
        lines.append(f"        season: {season}")
        lines.append(f"        episode: {episode}")
        if date_iso:
            lines.append(f'        originallyAvailableAt: "{date_iso}"')
        lines.append(f'        summary: "{_yaml_escape(summary)}"')

    yml_path.parent.mkdir(parents=True, exist_ok=True)
    yml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
