from __future__ import annotations

import re
from typing import Optional, Set, List, Tuple

from bs4 import BeautifulSoup

from .fetch import fetch_html
from .models import Episode


_YT_WATCH_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})", re.I
)
_YT_EMBED_RE = re.compile(r"youtube\.com/embed/([A-Za-z0-9_-]{6,})", re.I)


def _abs_url(href: str, base: str) -> str:
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return ""


def extract_youtube_url(soup: BeautifulSoup) -> Optional[str]:
    iframe = soup.find("iframe", src=_YT_EMBED_RE)
    if iframe and iframe.get("src"):
        m = _YT_EMBED_RE.search(iframe["src"])
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"

    html = soup.decode()
    m = _YT_WATCH_RE.search(html)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    m = _YT_EMBED_RE.search(html)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    return None


def clean_summary(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"[\.…]+$", "", s).strip()
    s = re.sub(r"(?i)\bpresented by\b[:\s].*$", "", s).strip()
    s = re.sub(r"[\.…]+$", "", s).strip()
    return s


def parse_episode_code(soup: BeautifulSoup, url: str) -> Tuple[str, int, int]:
    """
    Try hard to find SxxEyy. If missing, return S00E00.
    """
    text = soup.get_text(" ", strip=True)

    # Common formats: S2 E3, S02E03, Season 2 Episode 3, etc.
    m = re.search(r"\bS(\d{1,2})\s*E(\d{1,2})\b", text, re.I)
    if not m:
        m = re.search(r"\bSeason\s+(\d{1,2})\s+Episode\s+(\d{1,2})\b", text, re.I)

    if not m:
        return "S00E00", 0, 0

    season = int(m.group(1))
    ep = int(m.group(2))
    return f"S{season:02d}E{ep:02d}", season, ep


def extract_title(soup: BeautifulSoup) -> str:
    # Prefer <h1>, fallback to <title>
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(" ", strip=True)
        if t:
            return t
    ttag = soup.find("title")
    if ttag:
        t = ttag.get_text(" ", strip=True)
        if t:
            return t
    return "Unknown Title"


def extract_description(soup: BeautifulSoup) -> str:
    # Try meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    # Fallback: first substantial paragraph
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt and len(txt) > 40:
            return txt
    return ""


def extract_date_iso(soup: BeautifulSoup) -> Optional[str]:
    # Common patterns: <time datetime="YYYY-MM-DD"> etc.
    t = soup.find("time")
    if t and t.get("datetime"):
        dt = t["datetime"].strip()
        # keep YYYY-MM-DD if present
        m = re.match(r"(\d{4}-\d{2}-\d{2})", dt)
        return m.group(1) if m else dt
    return None


def discover_episode_urls(show_urls: List[str], *, site_base: str) -> List[str]:
    """
    Minimal discovery:
    - If the provided URLs are already episode pages, keep them.
    - If they are season/show pages, scrape links and collect likely episode links.
    This is intentionally conservative for now.
    """
    episode_urls: Set[str] = set()

    for url in show_urls:
        fr = fetch_html(url)
        if not fr.ok:
            continue

        soup = BeautifulSoup(fr.text, "lxml")

        # collect all links, then filter
        for a in soup.find_all("a", href=True):
            full = _abs_url(a["href"], site_base)
            if not full:
                continue

            # heuristic: episode pages often contain /episodes/ or /episode/
            if re.search(r"/episode[s]?/", full, re.I):
                episode_urls.add(full)

            # some sites are /shows/<slug>/season-x/<episode-slug>
            if re.search(r"/season-\d+/.+", full, re.I) and not re.search(
                r"/season-\d+/?$", full, re.I
            ):
                episode_urls.add(full)

        # If the URL itself looks like an episode page, keep it
        if re.search(r"/episode[s]?/", url, re.I):
            episode_urls.add(url)

    return sorted(episode_urls)


def fetch_episode(url: str) -> Optional[Episode]:
    fr = fetch_html(url)
    if not fr.ok:
        return None

    soup = BeautifulSoup(fr.text, "lxml")
    code, season, ep = parse_episode_code(soup, url)
    if code == "S00E00":
        return None

    title = extract_title(soup)
    desc = clean_summary(extract_description(soup))
    date_iso = extract_date_iso(soup)
    yt = extract_youtube_url(soup)

    return Episode(
        code=code,
        season=season,
        episode=ep,
        title=title,
        summary=desc,
        date_iso=date_iso,
        youtube=yt,
        source_url=url,
    )
