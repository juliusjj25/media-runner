from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, List, Dict

MIN_MATCH = 0.70

JUNK_PATTERNS = re.compile(
    r"\b("
    r"comedy|netflix|original|originals|netflix\s+originals|"
    r"480p|720p|1080p|2160p|hdr|dv|sdr|hybrid|repack|proper|internal|"
    r"web[- ]?dl|webrip|web|bluray|bdrip|hdrip|"
    r"h\.?264|h\.?265|x264|x265|hevc|avc|"
    r"ddp?(\+)?\s?5\.?1|dd\s?5\.?1|dd5\.?1|ddp?5\s?1|dd5\s?1|"
    r"aac\s?2\.?0|atmos|"
    r"nf|nordic|english"
    r")\b",
    re.IGNORECASE,
)

KNOWN_GROUPS = {
    "trolluhd",
    "flux",
    "edith",
    "rawr",
    "ntb",
    "khm",
    "playweb",
    "ethel",
    "norbit",
    "bioma",
    "strontium",
    "amrap",
    "qoq",
    "convoy",
    "jawn",
    "tepes",
    "npms",
    "ntg",
    "ffg",
    "revils",
    "prince",
}


def normalize_title(s: str) -> str:
    if not s:
        return ""
    s = str(s)
    s = re.sub(r"\.(mkv|mp4|m4v|avi)$", "", s, flags=re.I)
    s = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", s)
    s = s.replace("_", " ").replace(".", " ")
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s)
    s = re.sub(r"\b(19\d{2}|20\d{2})\b", " ", s)
    s = JUNK_PATTERNS.sub(" ", s)
    s = re.sub(r"\b(?:[A-Z]{3,}|[A-Z0-9]{3,})\b$", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    parts = s.split()
    if parts and parts[-1].lower() in KNOWN_GROUPS:
        parts = parts[:-1]
    return " ".join(parts).lower()


def extract_year(s: str) -> Optional[int]:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", s or "")
    return int(m.group(1)) if m else None


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def best_similarity(a: str, b: str) -> float:
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    direct = _ratio(a, b)
    a_tok = " ".join(sorted(a.split()))
    b_tok = " ".join(sorted(b.split()))
    token_sorted = _ratio(a_tok, b_tok)
    return max(direct, token_sorted)


def match_special(
    master: List[Dict], torrent_name: str, file_path: Path
) -> Optional[Dict]:
    t = (torrent_name or "").strip()
    stem = (file_path.stem or "").strip()

    if stem and t:
        t_cmp = normalize_title(t)
        stem_cmp = normalize_title(stem)
        hay_raw = f"{t} {stem}" if (stem_cmp and stem_cmp not in t_cmp) else t
    else:
        hay_raw = t or stem

    year = extract_year(hay_raw)
    hay_norm = normalize_title(hay_raw)

    candidates = master
    if year is not None:
        candidates = [r for r in master if r["season"] == year] or master

    best = None
    best_score = -1.0
    for r in candidates:
        score = best_similarity(hay_norm, r["title_cmp"])
        if score > best_score:
            best_score = score
            best = r

    if not best or best_score < MIN_MATCH:
        return None
    return best
