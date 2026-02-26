from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import portalocker


SEVERITY_ORDER = {"ok": 0, "changes": 1, "pending": 2, "error": 3}


def _now_dt() -> datetime:
    return datetime.now()


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _atomic_write_json(path: Path, data: dict) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _today_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def write_run_status(status_root: Path, line: str, kind: str) -> None:
    status_dir = Path(status_root)
    status_dir.mkdir(parents=True, exist_ok=True)

    # Current snapshot files (what your checker can read quickly)
    summary_current = status_dir / "summary_current.txt"
    status_current = status_dir / "status_current.json"

    # Window-stacked file
    from media_runner.core.timewindow import window_key

    wk = window_key(anchor_hour=8)
    window_file = status_dir / f"window_summary_{wk}.txt"

    # Maintain sticky severity + counts in status_current.json
    existing = {}
    if status_current.exists():
        try:
            existing = json.loads(status_current.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    counts = dict(existing.get("counts") or {})
    for k in ("ok", "changes", "pending", "error"):
        counts.setdefault(k, 0)
    if kind not in counts:
        counts[kind] = 0
    counts[kind] += 1

    prev_status = existing.get("window_status", "ok")
    new_status = prev_status
    if SEVERITY_ORDER.get(kind, 0) > SEVERITY_ORDER.get(prev_status, 0):
        new_status = kind

    # Update snapshot
    _atomic_write_text(summary_current, line.strip() + "\n")

    now = datetime.now()
    payload = {
        "window_status": new_status,
        "counts": counts,
        "last_update_local": now.strftime("%Y-%m-%d %H:%M:%S"),
        "stale": False,
        "last_line": line.strip(),
        "window_key": wk,
    }
    _atomic_write_json(status_current, payload)

    # Append to window file with a lock so parallel runs don't collide (Windows-safe: write via lock handle)
    window_file.parent.mkdir(parents=True, exist_ok=True)
    with portalocker.Lock(
        str(window_file),
        mode="a",
        timeout=10,
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(f"{_now_str()} {line.strip()}\n")
