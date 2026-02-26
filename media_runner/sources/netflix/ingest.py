from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal

from media_runner.core.fileops import (
    find_video_files,
    pick_primary_video,
    safe_path_name,
    create_hardlink,
)

from .master import refresh_master, load_master_csv
from .match import match_special

Status = Literal["ok", "changes", "pending", "error"]


@dataclass
class NetflixIngestResult:
    status: Status
    message: str
    season: Optional[int] = None
    episode: Optional[int] = None
    title: Optional[str] = None
    wiki_ok: bool = True


def build_dest_folder(library_root: Path, season: int) -> Path:
    return library_root / f"Netflix Stand Up Specials S{season}"


def build_dest_filename(season: int, episode: int, title: str, suffix: str) -> str:
    title = (title or "").replace(": ", " - ")
    base = f"Netflix Stand Up Specials - S{season}E{episode:02d} - {title}"
    base = re.sub(r"\s*-\s*", " - ", base).strip()
    return f"{safe_path_name(base)}{suffix.lower()}"


def ingest_netflix_standup(
    category: str,
    torrent_name: str,
    content_path: Path,
    *,
    category_allow: str,
    library_root: Path,
    master_csv: Path,
    master_json: Path | None = None,
    kometa_metadata_dir: Path | None = None,
    kometa_yml_name: str | None = None,
    plex_show_title: str = "Netflix Stand Up Specials",
    dry_run: bool = False,
) -> NetflixIngestResult:

    # Ignore non-matching category silently
    if category.strip() != category_allow:
        return NetflixIngestResult(status="ok", message="")

    # Validate content path
    if not content_path.exists():
        return NetflixIngestResult(
            status="error",
            message=f"Error: Content path does not exist: {content_path}",
        )

    # Refresh master (safe fallback if it fails)
    wiki_res = refresh_master(
        master_csv=master_csv,
        master_json=master_json,
        kometa_metadata_dir=kometa_metadata_dir,
        kometa_yml_name=kometa_yml_name,
        plex_show_title=plex_show_title,
    )

    wiki_ok = wiki_res.ok

    # If refresh failed AND CSV doesn't exist, hard stop
    if not master_csv.exists() and not wiki_ok:
        return NetflixIngestResult(
            status="error",
            message="Error: Master list missing and refresh failed.",
        )

    # Load master list
    try:
        master = load_master_csv(master_csv)
    except Exception as e:
        return NetflixIngestResult(
            status="error",
            message=f"Error: Failed to load master CSV: {e}",
            wiki_ok=wiki_ok,
        )

    # Find primary video file
    vids = find_video_files(content_path)
    primary = pick_primary_video(vids)
    if primary is None:
        return NetflixIngestResult(
            status="error",
            message=f"Error: No video files found under: {content_path}",
            wiki_ok=wiki_ok,
        )

    # Match against master
    match = match_special(master, torrent_name, primary)
    if match is None:
        return NetflixIngestResult(
            status="pending",
            message="Pending Approval: Content Requires Approval",
            wiki_ok=wiki_ok,
        )

    season = int(match["season"])
    episode = int(match["episode"])
    title = str(match["title"])

    dest_folder = build_dest_folder(library_root, season)
    dest_name = build_dest_filename(season, episode, title, primary.suffix)
    dest = dest_folder / dest_name

    # Create hardlink
    try:
        create_hardlink(primary, dest, dry_run=dry_run)
    except Exception as e:
        return NetflixIngestResult(
            status="error",
            message=f"Error: Hardlink failed: {e}",
            wiki_ok=wiki_ok,
        )

    suffix = "; Wiki Error" if not wiki_ok else ""

    return NetflixIngestResult(
        status="changes",
        message=f"Changes: New Episodes: NetflixStandUp: S{season}E{episode:02d}{suffix}",
        season=season,
        episode=episode,
        title=title,
        wiki_ok=wiki_ok,
    )
