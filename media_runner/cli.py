import argparse
from datetime import datetime
from pathlib import Path
from media_runner.sources.netflix.ingest import ingest_netflix_standup
from media_runner.core.status import write_run_status
from media_runner.core.timewindow import window_start_local
from media_runner.config.load import load_config


def main() -> int:
    parser = argparse.ArgumentParser(prog="media-runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # -------------------------
    # status commands
    # -------------------------
    st = sub.add_parser("status", help="write status / summary outputs")
    st_sub = st.add_subparsers(dest="status_cmd", required=True)

    # status ping (manual test)
    ping = st_sub.add_parser("ping", help="write a test status entry")
    ping.add_argument(
        "--kind", choices=["ok", "changes", "pending", "error"], default="ok"
    )
    ping.add_argument("--msg", default="", help="optional message override")

    # status heartbeat (stale-aware OK)
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

    nf = ing_sub.add_parser(
        "netflix", help="handle qBittorrent NetflixStandUp completion"
    )
    nf.add_argument("category")
    nf.add_argument("torrent_name")
    nf.add_argument("content_path")
    nf.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    runtime_dir = repo_root / "runtime"
    cfg = load_config(runtime_dir)

    # -------------------------
    # status ping
    # -------------------------
    if args.cmd == "status" and args.status_cmd == "ping":
        # minimal messages, per your spec
        since = window_start_local(anchor_hour=8).strftime("%m-%d-%Y")

        if args.kind == "ok":
            line = args.msg or f"OK Heartbeat: No changes since {since}"
        elif args.kind == "changes":
            line = args.msg or "Changes: New Episodes: MeatEater: S01E03"
        elif args.kind == "pending":
            line = args.msg or "Pending Approval: Content Requires Approval"
        else:
            line = args.msg or "Error: An Error Occurred"

        write_run_status(status_root=cfg.status_root, line=line, kind=args.kind)
        print(f"Wrote status: {line}")
        return 0

    # -------------------------
    # status heartbeat (stale check)
    # -------------------------
    if args.cmd == "status" and args.status_cmd == "heartbeat":
        status_dir = cfg.status_root
        status_current = status_dir / "status_current.json"

        # Determine "since" using your 8AM window anchor
        anchor = args.anchor_hour if "anchor_hour" in vars(args) else cfg.anchor_hour
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
                reason = (
                    f"status_current.json mtime older than {args.stale_hours} hours"
                )

        if stale:
            line = "Error: An Error Occurred"
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(f"Heartbeat wrote ERROR (stale): {reason}")
            return 2

        line = f"OK Heartbeat: No changes since {since}"
        write_run_status(status_root=cfg.status_root, line=line, kind="ok")
        print(f"Wrote heartbeat: {line}")
        return 0

    # -------------------------
    # ingest netflix
    # -------------------------
    if args.cmd == "ingest" and args.ingest_cmd == "netflix":
        # TEMP: hardcoded Netflix paths (we’ll move to config next)
        if not cfg.netflix:
            line = "Error: Netflix config missing in runtime/config.toml"
            write_run_status(status_root=cfg.status_root, line=line, kind="error")
            print(line)
            return 2

        category_allow = cfg.netflix.category_allow
        library_root = cfg.netflix.library_root
        master_csv = cfg.netflix.master_csv
        wiki_scraper = cfg.netflix.wiki_scraper

        res = ingest_netflix_standup(
            category=args.category,
            torrent_name=args.torrent_name,
            content_path=Path(str(args.content_path).strip().strip('"')),
            category_allow=category_allow,
            library_root=library_root,
            master_csv=master_csv,
            wiki_scraper=wiki_scraper,
            dry_run=args.dry_run,
        )

        # Write to your existing status system
        if res.message:
            write_run_status(
                status_root=cfg.status_root, line=res.message, kind=res.status
            )
            print(res.message)
        return 0 if res.status != "error" else 2

    # If we got here, args didn't match a handler
    print("Unknown command.")
    return 1
