from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib as tomli  # Python 3.11+
except ModuleNotFoundError:
    import tomli  # Python 3.9/3.10


@dataclass
class NetflixConfig:
    category_allow: str
    library_root: Path
    master_csv: Path
    wiki_scraper: Path


@dataclass
class AppConfig:
    status_root: Path
    anchor_hour: int = 8
    stale_hours: float = 26.0
    netflix: NetflixConfig | None = None


def load_config(runtime_dir: Path) -> AppConfig:
    cfg_path = runtime_dir / "config.toml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Missing config file: {cfg_path}")

    data = tomli.loads(cfg_path.read_text(encoding="utf-8"))
    paths = data.get("paths", {})

    status_root = Path(paths.get("status_root", str(runtime_dir / "status")))
    anchor_hour = int(paths.get("anchor_hour", 8))
    stale_hours = float(paths.get("stale_hours", 26.0))

    nf = data.get("netflix")
    netflix_cfg = None

    if isinstance(nf, dict):
        required = ["library_root", "master_csv", "wiki_scraper"]
        missing = [k for k in required if k not in nf]
        if missing:
            raise ValueError(f"Missing [netflix] keys in config.toml: {missing}")

        netflix_cfg = NetflixConfig(
            category_allow=str(nf.get("category_allow", "NetflixStandUp")),
            library_root=Path(str(nf["library_root"])),
            master_csv=Path(str(nf["master_csv"])),
            wiki_scraper=Path(str(nf["wiki_scraper"])),
        )

    return AppConfig(
        status_root=status_root,
        anchor_hour=anchor_hour,
        stale_hours=stale_hours,
        netflix=netflix_cfg,
    )
