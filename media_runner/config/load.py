from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib as tomli
except ModuleNotFoundError:
    import tomli


@dataclass
class NetflixConfig:
    category_allow: str
    library_root: Path
    master_csv: Path
    master_json: Path | None = None
    kometa_metadata_dir: Path | None = None
    kometa_yml_name: str | None = None
    plex_show_title: str = "Netflix Stand Up Specials"


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
        netflix_cfg = NetflixConfig(
            category_allow=str(nf.get("category_allow", "NetflixStandUp")),
            library_root=Path(str(nf["library_root"])),
            master_csv=Path(str(nf["master_csv"])),
            master_json=Path(str(nf["master_json"])) if nf.get("master_json") else None,
            kometa_metadata_dir=(
                Path(str(nf["kometa_metadata_dir"]))
                if nf.get("kometa_metadata_dir")
                else None
            ),
            kometa_yml_name=(
                str(nf["kometa_yml_name"]) if nf.get("kometa_yml_name") else None
            ),
            plex_show_title=str(nf.get("plex_show_title", "Netflix Stand Up Specials")),
        )

    return AppConfig(
        status_root=status_root,
        anchor_hour=anchor_hour,
        stale_hours=stale_hours,
        netflix=netflix_cfg,
    )
