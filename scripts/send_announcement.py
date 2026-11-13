"""
Send an announcement e-mail campaign (default: the 2027 launch e-mail).

Nothing is sent unless --apply is given. Addresses that unsubscribed are skipped, and every
address that was sent is recorded, so the script can be stopped and re-run without duplicates.

Usage (uses the same settings as the API):
    python -m scripts.send_announcement                       # dry run: counts only
    python -m scripts.send_announcement --to me@example.com   # one test e-mail, not recorded
    python -m scripts.send_announcement --to me@example.com --lang EN
    python -m scripts.send_announcement --apply --limit 20    # first 20 recipients
    python -m scripts.send_announcement --apply               # everyone left
    python -m scripts.send_announcement --audience all        # users + everyone who joined a draw

--rate is e-mails per second (default 5); keep it under the SES sending rate of the account.
"""
import argparse
import sys
import time
from collections import Counter

from app.config import settings
from app.models.database import SessionLocal
from app.services.announcement_service import AUDIENCE_ALL, AUDIENCE_USERS, collect_recipients, mark_sent
from app.services.email_service import EmailService

DEFAULT_CAMPAIGN = "2027-launch"


def _links_are_public() -> bool:
    return not any(host in url for url in (settings.api_url, settings.frontend_url) for host in ("localhost", "127.0.0.1"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an announcement e-mail campaign")
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--audience", choices=[AUDIENCE_USERS, AUDIENCE_ALL], default=AUDIENCE_USERS)
    parser.add_argument("--apply", action="store_true", help="actually send; without it this is a dry run")
    parser.add_argument("--to", help="send a single test e-mail to this address (not recorded)")
    parser.add_argument("--lang", default="TR", choices=["TR", "EN", "tr", "en"], help="language for --to")
    parser.add_argument("--limit", type=int, default=0, help="send to at most this many recipients")
    parser.add_argument("--rate", type=float, default=5.0, help="e-mails per second")
    args = parser.parse_args()

    if args.campaign not in EmailService.ANNOUNCEMENT_CONFIG:
        print(f"Unknown campaign '{args.campaign}'. Known: {', '.join(EmailService.ANNOUNCEMENT_CONFIG)}")
        return 2

    if (args.apply or args.to) and not _links_are_public():
        print(
            "API_URL / FRONTEND_URL point at localhost, so the links and images in the e-mail would be broken.\n"
            f"  API_URL={settings.api_url}\n  FRONTEND_URL={settings.frontend_url}\nNothing sent."
        )
        return 2

    if args.to:
        ok = EmailService().send_announcement_email(args.campaign, args.to, args.lang.upper())
        print(f"Test e-mail to {args.to}: {'sent' if ok else 'FAILED'}")
        return 0 if ok else 1

    db = SessionLocal()
    try:
        recipients = collect_recipients(db, args.campaign, args.audience)
        if args.limit:
            recipients = recipients[: args.limit]
        by_language = Counter(language for _, language in recipients)
        print(f"Campaign '{args.campaign}', audience '{args.audience}': {len(recipients)} recipients {dict(by_language)}")

        if not args.apply:
            print("Dry run - nothing sent. Re-run with --apply to send.")
            return 0

        service = EmailService()
        delay = 1.0 / args.rate if args.rate > 0 else 0
        sent = failed = 0
        for email, language in recipients:
            if service.send_announcement_email(args.campaign, email, language):
                mark_sent(db, args.campaign, email)
                sent += 1
            else:
                failed += 1
            if (sent + failed) % 50 == 0:
                print(f"  {sent + failed}/{len(recipients)} processed ({failed} failed)")
            time.sleep(delay)
        print(f"Done: {sent} sent, {failed} failed. Failed addresses are not recorded; re-run to retry them.")
        return 0 if failed == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
