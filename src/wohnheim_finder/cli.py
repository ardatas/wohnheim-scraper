from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .categories import CATEGORIES, category_label
from .campaigns import generate_weekly_campaign
from .config import load_yaml
from .discover import discover
from .drafts import generate_due_drafts
from .review_server import serve_dashboard
from .store import (
    connect,
    get_setting,
    init_db,
    list_messages,
    list_residences,
    set_setting,
    update_message_status,
)
from .utils import now_iso

DEFAULT_DB = "data/outreach.sqlite"
DEFAULT_SOURCES = "config/sources.yaml"
DEFAULT_APPLICANT = "config/applicant.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wohnheim")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("categories", help="Show category taxonomy")

    p_discover = sub.add_parser("discover", help="Import seed findings and scrape configured source pages")
    p_discover.add_argument("--sources", default=DEFAULT_SOURCES)
    p_discover.add_argument("--no-fetch", action="store_true", help="Only import local seed CSV/manual entries")

    p_list = sub.add_parser("list", help="List residences by category")
    p_list.add_argument("--all", action="store_true", help="Include closed/inactive entries")

    p_drafts = sub.add_parser("generate-drafts", help="Generate initial and due follow-up drafts")
    p_drafts.add_argument("--applicant", default=DEFAULT_APPLICANT)
    p_drafts.add_argument("--outbox", default="outbox")
    p_drafts.add_argument("--follow-up-days", type=int, default=3)
    p_drafts.add_argument("--ai", action="store_true", help="Use DeepSeek or another OpenAI-compatible API for generated variants")
    p_drafts.add_argument("--limit", type=int)

    p_weekly = sub.add_parser(
        "generate-weekly-campaign",
        help="Generate one weekly base mail and one tailored mail per residence category",
    )
    p_weekly.add_argument("--applicant", default=DEFAULT_APPLICANT)
    p_weekly.add_argument("--campaigns-dir", default="campaigns")
    p_weekly.add_argument("--outbox", default="outbox")
    p_weekly.add_argument("--ai", action="store_true", help="Use DeepSeek or another OpenAI-compatible API")
    p_weekly.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Limit generation to one category; may be passed multiple times",
    )
    p_weekly.add_argument("--no-drafts", action="store_true", help="Only save base/category mails; do not create dashboard drafts")

    p_messages = sub.add_parser("messages", help="List generated messages")
    p_messages.add_argument("--status", choices=["draft", "approved", "sent", "skipped", "error"])

    p_mark = sub.add_parser("mark-sent", help="Mark a draft sent after you sent it manually")
    p_mark.add_argument("message_id", type=int)

    sub.add_parser("stop", help="Pause outreach/follow-up generation")
    sub.add_parser("resume", help="Resume outreach/follow-up generation")

    p_serve = sub.add_parser("serve", help="Start local manual review dashboard")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    init_db(conn)

    if args.command == "categories":
        for key, label in CATEGORIES.items():
            print(f"{key}: {label}")
        return

    if args.command == "discover":
        stats = discover(args.sources, args.db, fetch=not args.no_fetch)
        print(f"Seeded {stats['seeded']} entries; scraped {stats['scraped']} candidates; failed sources {stats['failed_sources']}.")
        return

    if args.command == "list":
        rows = list_residences(conn, include_inactive=args.all)
        current = None
        for row in rows:
            if row["category"] != current:
                current = row["category"]
                print(f"\n[{current}] {category_label(current)}")
            email = f" <{row['email']}>" if row["email"] else ""
            status = f" ({row['status']})" if row["status"] != "active" else ""
            print(f"- #{row['id']} {row['name']}{email}{status}")
        return

    if args.command == "generate-drafts":
        if get_setting(conn, "outreach_paused", "false") == "true":
            print("Outreach is paused. Run `wohnheim resume` to draft again.")
            return
        applicant_path = Path(args.applicant)
        if not applicant_path.exists():
            print(
                f"Applicant profile missing: {applicant_path}. Copy config/applicant.example.yaml to config/applicant.yaml and fill truthful facts.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        stats = generate_due_drafts(
            conn,
            applicant_path,
            outbox_dir=args.outbox,
            follow_up_days=args.follow_up_days,
            use_ai=args.ai,
            limit=args.limit,
        )
        print(
            f"Drafted {stats['initial']} initial emails and {stats['follow_up']} follow-ups; skipped {stats['skipped']}."
        )
        return

    if args.command == "generate-weekly-campaign":
        if get_setting(conn, "outreach_paused", "false") == "true":
            print("Outreach is paused. Run `wohnheim resume` to draft again.")
            return
        applicant_path = Path(args.applicant)
        if not applicant_path.exists():
            print(
                f"Applicant profile missing: {applicant_path}. Copy config/applicant.example.yaml to config/applicant.yaml and fill truthful facts.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        result = generate_weekly_campaign(
            conn,
            applicant_path,
            campaigns_dir=args.campaigns_dir,
            outbox_dir=args.outbox,
            use_ai=args.ai,
            create_drafts=not args.no_drafts,
            limit_categories=args.categories,
        )
        print(f"Generated weekly campaign {result.week_id}/{result.timestamp}.")
        print(f"Base mail: {result.base_path}")
        print("Category mails:")
        for category, path in result.category_paths.items():
            print(f"- {category}: {path}")
        print(f"Created {result.drafts_created} dashboard drafts; skipped {result.skipped}.")
        return

    if args.command == "messages":
        for row in list_messages(conn, status=args.status):
            to_email = row["email"] or "(website/form)"
            print(f"#{row['id']} {row['status']} {row['kind']} -> {row['name']} {to_email}: {row['subject']}")
        return

    if args.command == "mark-sent":
        update_message_status(conn, args.message_id, "sent", {"sent_at": now_iso()})
        print(f"Marked message #{args.message_id} sent.")
        return

    if args.command == "stop":
        set_setting(conn, "outreach_paused", "true")
        print("Outreach paused. No follow-up drafts will be generated until resume.")
        return

    if args.command == "resume":
        set_setting(conn, "outreach_paused", "false")
        print("Outreach resumed.")
        return

    if args.command == "serve":
        serve_dashboard(args.db, host=args.host, port=args.port)
        return


if __name__ == "__main__":
    main()
