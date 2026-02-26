import argparse
from datetime import datetime
from pathlib import Path

from media_runner.config.load import load_config
from media_runner.core.status import write_run_status
from media_runner.core.timewindow import window_start_local

from media_runner.sources.netflix.ingest import ingest_netflix_standup
from media_runner.sources.netflix.master import refresh_master

# MeatEater
try:
    from media_runner.sources.meateater.ingest import scrape_meateater
except Exception:
    scrape_meateater = None  # keeps CLI importable even if you haven't built it yet


def main() -> int:
    parser = argparse.ArgumentParser(prog="media-runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # -------------------------
    # status commands
    # -------------------------
    st = sub.add_parser("status", help="write status / summary outputs")
    st_sub = st.add_subparsers(dest="status_cmd", required=True)

    ping = st_sub.add_parser("ping", help="write a test status entry")
    ping.add_argument(
        "--kind", choices=["ok", "changes", "pending", "error"], default="ok"
    )
    ping.add_argument("--msg", default="", help="optional message override")

    hb = st_sub.add_parser(
        "heartbeat", help="write OK heartbeat unless status is stale"
    )
    hb.add_argument(
        "--stale-hours",
        type=float,
        default=26.0,
        help="mark stale if last update older than this",
    )
    hb.add_argument(
        "--anchor-hour", type=int, default=8, help="window start hour (local)"
    )

    # -------------------------
    # ingest commands
    # -------------------------
    ing = sub.add_parser("ingest", help="ingest hooks")
    ing_sub = ing.add_subparsers(dest="ingest_cmd", required=True)

    nf_ing = ing_sub.add_parser(
        "netflix", help="handle qBittorrent NetflixStandUp completion"
    )
    nf_ing.add_argument("category")
    nf_ing.add_argument("torrent_name")
    nf_ing.add_argument("content_path")
    nf_ing.add_argument("--dry-run", action="store_true")

    # -------------------------
    # netflix utilities
    # -------------------------
    nf = sub.add_parser("netflix", help="netflix utilities")
    nf_sub = nf.add_subparsers(dest="netflix_cmd", required=True)

    rm = nf_sub.add_parser(
        "refresh-master",
        help="refresh Netflix master list from Wikipedia and write Kometa YAML",
    )
    rm.add_argument(
        "--force", action="store_true", help="treat as changes even if counts match"
    )

    # -------------------------
    # meateater utilities
    # -------------------------
    me = sub.add_parser("meateater", help="meateater utilities")
    me_sub = me.add_subparsers(dest="meateater_cmd", required=True)

    me_scrape = me_sub.add_parser(
        "scrape",
        help="scrape meateater site -> update Kometa YAML -> emit pending approvals",
    )
    me_scrape.add_argument(
        "--no-review",
        action="store_true",
        help="disable review mode (later: auto-queue). For now still writes YAML.",
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    runtime_dir = repo_root / "runtime"
    cfg = load_config(runtime_dir)

    # -------------------------
    # status ping
    # -------------------------
    if args.cmd == "status" and args.status_cmd == "ping":
        since = window_start_local(anchor_hour=cfg.anchor_hour).strftime("%m-%d-%Y")

        if args.kind == "ok":
            line = args.msg or f"OK Heartbeat: No changes since {since}"
        elif args.kind == "changes":
            line = args.msg or "Changes: New Episodes: MeatEater: S01E03"
        elif args.kind == "pending":
            line = args.msg or "Pending Approval: Content Requires Approval"
        else:
            line = args.msg or "Error: An Error Occurred"

        write_run_status(status_root=cfg.status_root, line=line, kind=args.kind)
        print(line)
        return 0

    # -------------------------
    # status heartbeat (stale check)
    # -------------------------
    if args.cmd == "status" and args.status_cmd == "heartbeat":
        status_current = cfg.status_root / "status_current.json"

        anchor = args.anchor_hour if args.anchor_hour is not None else cfg.anchor_hour
        since = window_start_local(anchor_hour=anchor).strftime("%m-%d-%Y")

        stale = False
        reason = ""

        if not status_current.exists():
            stale = True
            reason = "missing status_current.json"
        else:
            age_seconds = datetime.now().timestamp() - status_current.stat().st_mtime
            if age_seconds > (args.stale_hours * 3600):
                stale = True
                reason = f"status_current.json older than {args.stale_hours} hours"

        if stale:
            line = "Error: An Error Occurred"
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(f"{line} (stale: {reason})")
            return 2

        line = f"OK Heartbeat: No changes since {since}"
        write_run_status(status_root=cfg.status_root, line=line, kind="ok")
        print(line)
        return 0

    # -------------------------
    # ingest netflix
    # -------------------------
    if args.cmd == "ingest" and args.ingest_cmd == "netflix":
        if not cfg.netflix:
            line = "Error: Netflix config missing in runtime/config.toml"
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(line)
            return 2

        res = ingest_netflix_standup(
            category=args.category,
            torrent_name=args.torrent_name,
            content_path=Path(str(args.content_path).strip().strip('"')),
            category_allow=cfg.netflix.category_allow,
            library_root=cfg.netflix.library_root,
            master_csv=cfg.netflix.master_csv,
            master_json=getattr(cfg.netflix, "master_json", None),
            kometa_metadata_dir=getattr(cfg.netflix, "kometa_metadata_dir", None),
            kometa_yml_name=getattr(cfg.netflix, "kometa_yml_name", None),
            plex_show_title=getattr(
                cfg.netflix, "plex_show_title", "Netflix Stand Up Specials"
            ),
            dry_run=args.dry_run,
        )

        if res.message:
            write_run_status(
                status_root=cfg.status_root, line=res.message, kind=res.status
            )
            print(res.message)

        return 0 if res.status != "error" else 2

    # -------------------------
    # netflix refresh-master
    # -------------------------
    if args.cmd == "netflix" and args.netflix_cmd == "refresh-master":
        if not cfg.netflix:
            line = "Error: Netflix config missing in runtime/config.toml"
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(line)
            return 2

        res = refresh_master(
            master_csv=cfg.netflix.master_csv,
            master_json=getattr(cfg.netflix, "master_json", None),
            kometa_metadata_dir=getattr(cfg.netflix, "kometa_metadata_dir", None),
            kometa_yml_name=getattr(cfg.netflix, "kometa_yml_name", None),
            plex_show_title=getattr(
                cfg.netflix, "plex_show_title", "Netflix Stand Up Specials"
            ),
        )

        if not res.ok:
            line = "Error: Netflix master refresh failed"
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(line)
            if getattr(res, "reason", ""):
                print("Reason:", res.reason)
            return 2

        changed = bool(getattr(res, "changed", False)) or args.force
        if changed:
            before = getattr(res, "count_before", "?")
            after = getattr(res, "count_after", "?")
            line = f"Changes: Netflix master refreshed ({before} -> {after})"
            kind = "changes"
        else:
            since = window_start_local(anchor_hour=cfg.anchor_hour).strftime("%m-%d-%Y")
            line = f"OK Heartbeat: No changes since {since}"
            kind = "ok"

        write_run_status(status_root=cfg.status_root, line=line, kind=kind)
        print(line)
        return 0

    # -------------------------
    # meateater scrape
    # -------------------------
    if args.cmd == "meateater" and args.meateater_cmd == "scrape":
        if scrape_meateater is None:
            line = "Error: MeatEater module not available (missing sources/meateater code)."
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(line)
            return 2

        if not getattr(cfg, "meateater", None):
            line = "Error: MeatEater config missing in runtime/config.toml"
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(line)
            return 2

        res = scrape_meateater(
            shows=cfg.meateater.shows,
            site_base=cfg.meateater.site_base,
            output_metadata_dir=cfg.meateater.output_metadata_dir,
            approvals_dir=cfg.meateater.approvals_dir,
            always_review=(not args.no_review),
        )

        if res.message:
            write_run_status(
                status_root=cfg.status_root, line=res.message, kind=res.status
            )
            print(res.message)

        return 0 if res.status != "error" else 2

    print("Unknown command.")
    return 1
