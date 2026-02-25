from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Iterable, Set

DEFAULT_VIDEO_EXTS: Set[str] = {".mkv", ".mp4", ".m4v", ".avi"}


def find_video_files(
    content_path: Path, video_exts: Iterable[str] = DEFAULT_VIDEO_EXTS
) -> List[Path]:
    exts = {e.lower() for e in video_exts}
    if content_path.is_file():
        return [content_path] if content_path.suffix.lower() in exts else []
    vids: List[Path] = []
    for p in content_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            vids.append(p)
    return vids


def pick_primary_video(vids: List[Path]) -> Optional[Path]:
    if not vids:
        return None
    return max(vids, key=lambda p: p.stat().st_size)


def same_filesystem(a: Path, b: Path) -> bool:
    return a.drive.lower() == b.drive.lower()


def safe_path_name(name: str) -> str:
    # Basic Windows-unsafe char replacement
    return re.sub(r'[<>:"/\\|?*]', " - ", (name or "")).strip()


def create_hardlink(src: Path, dest: Path, dry_run: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        return

    if not same_filesystem(src, dest):
        raise RuntimeError(
            f"Cannot hardlink across volumes: src={src.drive} dest={dest.drive}"
        )

    if dry_run:
        return

    os.link(str(src), str(dest))
