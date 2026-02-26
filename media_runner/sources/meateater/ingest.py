from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Literal, Any

from .parse import discover_episode_urls, fetch_episode
from .kometa_yaml import merge_with_existing, write_show_yaml

Status = Literal["ok", "changes", "pending", "error"]


@dataclass
class MeateaterResult:
    status: Status
    message: str
    new_by_show: Dict[str, List[str]]
    pending_count: int = 0


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def scrape_meateater(
    *,
    shows: List[Dict[str, Any]],
    site_base: str,
    output_metadata_dir: Path,
    approvals_dir: Path,
    always_review: bool = True,
) -> MeateaterResult:
    """
    shows entries:
      { "name": "MeatEater Hunts", "year": 2012, "urls": [...], "yml": "meateater_hunts.yml" }

    output_metadata_dir: where to write per-show Kometa YAML files (on this machine)
    approvals_dir: where to drop pending approvals JSON for your webui later
    """
    if not shows:
        return MeateaterResult(
            status="error",
            message="Error: No MeatEater shows configured.",
            new_by_show={},
        )

    new_by_show: Dict[str, List[str]] = {}
    pending_items: List[Dict[str, Any]] = []

    for show in shows:
        name = str(show.get("name", "")).strip()
        year = int(show.get("year", 0) or 0)
        urls = list(show.get("urls", []) or [])
        yml_name = str(show.get("yml", "")).strip() or f"{name}.yml"

        if not name or not urls or year <= 0:
            return MeateaterResult(
                status="error",
                message=f"Error: Invalid show config (need name/year/urls): {show}",
                new_by_show=new_by_show,
            )

        # Discover episode URLs
        ep_urls = discover_episode_urls(urls, site_base=site_base)
        if not ep_urls:
            continue

        # Fetch episodes
        episodes_map: Dict[str, Dict[str, Any]] = {}
        for u in ep_urls:
            ep = fetch_episode(u)
            if not ep:
                continue
            episodes_map[ep.code] = {
                "season": ep.season,
                "episode": ep.episode,
                "title": ep.title,
                "date_iso": ep.date_iso,
                "summary": ep.summary or "",
                "youtube": ep.youtube,
                "source_url": ep.source_url,
            }

        # Merge with existing YAML and write it
        yml_path = output_metadata_dir / yml_name
        merge = merge_with_existing(yml_path, name, episodes_map)
        write_show_yaml(
            yml_path,
            show_name=name,
            year=year,
            episodes_by_code=merge.merged,
            extra_show_meta=merge.extra_show_meta,
        )

        if merge.new_codes:
            new_by_show[name] = merge.new_codes

            # Only queue things that have youtube links. Otherwise they can exist as metadata only.
            for code in merge.new_codes:
                item = merge.merged.get(code, {})
                if item.get("youtube"):
                    pending_items.append(
                        {
                            "show": name,
                            "code": code,
                            "title": item.get("title", ""),
                            "youtube": item.get("youtube"),
                            "source_url": item.get("source_url"),
                        }
                    )

    if not new_by_show:
        return MeateaterResult(
            status="ok",
            message="OK Heartbeat: No changes since today",
            new_by_show={},
            pending_count=0,
        )

    # Always-review: dump pending approvals
    if always_review and pending_items:
        pending_path = approvals_dir / "meateater_pending.json"
        existing = _load_json(pending_path) or []
        if not isinstance(existing, list):
            existing = []

        # de-dupe by (show, code)
        seen = {(x.get("show"), x.get("code")) for x in existing if isinstance(x, dict)}
        for it in pending_items:
            key = (it["show"], it["code"])
            if key not in seen:
                existing.append(it)
                seen.add(key)

        _write_json(pending_path, existing)

        return MeateaterResult(
            status="pending",
            message=f"Pending Approval: {len(pending_items)} new YouTube episodes",
            new_by_show=new_by_show,
            pending_count=len(pending_items),
        )

    # If not review mode, we’ll wire queue writing later
    return MeateaterResult(
        status="changes",
        message="Changes: New episodes discovered (review disabled)",
        new_by_show=new_by_show,
    )
