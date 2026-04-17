#!/usr/bin/env python3
"""Watch beta.gouv.fr jobs on Welcome to the Jungle and email new ones.

Queries the public WTJ Algolia index for the organization, diffs against
state.json, and sends one email listing all newly appeared jobs. The
first run (when state.json doesn't exist yet) seeds state without emailing.

Env vars:
  SMTP_HOST        default smtp.gmail.com
  SMTP_PORT        default 465 (SSL). 587 switches to STARTTLS.
  SMTP_USER        required unless --dry-run
  SMTP_PASS        required unless --dry-run
  MAIL_FROM        default = SMTP_USER
  MAIL_TO          required unless --dry-run. Comma-separated allowed.

Flags:
  --dry-run   Print what would be emailed, touch no files, send no mail.
  --seed      Write state.json from the current listing and exit (no email).
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

ALGOLIA_APP_ID = "CSEKHVMS53"
# Public search-only key used by welcometothejungle.com itself. Safe to ship.
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
ALGOLIA_INDEX = "wk_cms_jobs_production"
ALGOLIA_URL = (
    f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
)

ORG_SLUG_IN_INDEX = "communaute-beta-gout"  # note: index has this typo
ORG_SLUG_PUBLIC = "communaute-beta-gouv"
JOB_URL_TMPL = f"https://www.welcometothejungle.com/fr/companies/{ORG_SLUG_PUBLIC}/jobs/{{slug}}"

STATE_PATH = Path(__file__).parent / "state.json"


def fetch_jobs() -> list[dict]:
    payload = json.dumps(
        {
            "filters": f'organization.slug:"{ORG_SLUG_IN_INDEX}" AND website.reference:wttj_fr',
            "hitsPerPage": 100,
        }
    ).encode()
    req = urllib.request.Request(
        ALGOLIA_URL,
        data=payload,
        method="POST",
        headers={
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
            "X-Algolia-API-Key": ALGOLIA_API_KEY,
            "Content-Type": "application/json",
            "Referer": "https://www.welcometothejungle.com/",
            "Origin": "https://www.welcometothejungle.com",
            "User-Agent": "crawl-beta-gouv/1.0 (+https://github.com)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data.get("hits", [])


def summarize(job: dict) -> dict:
    office = job.get("office") or {}
    offices = job.get("offices") or []
    cities = sorted({(o.get("city") or "").strip() for o in offices if o.get("city")})
    if not cities and office.get("city"):
        cities = [office["city"]]
    return {
        "ref": job.get("reference"),
        "title": job.get("name") or "(sans titre)",
        "slug": job.get("slug"),
        "contract": (job.get("contract_type_names") or {}).get("fr")
        or job.get("contract_type")
        or "",
        "cities": ", ".join(cities),
        "remote": job.get("remote") or "",
        "published_at": job.get("published_at") or "",
        "url": JOB_URL_TMPL.format(slug=job.get("slug", "")),
    }


def load_state() -> set[str] | None:
    if not STATE_PATH.exists():
        return None
    raw = json.loads(STATE_PATH.read_text())
    return set(raw.get("known_refs", []))


def save_state(refs: set[str]) -> None:
    STATE_PATH.write_text(
        json.dumps({"known_refs": sorted(refs)}, indent=2, ensure_ascii=False) + "\n"
    )


def render_email(new_jobs: list[dict]) -> tuple[str, str, str]:
    n = len(new_jobs)
    plural = "s" if n > 1 else ""
    subject = f"[beta.gouv.fr] {n} nouvelle{plural} offre{plural} sur Welcome to the Jungle"

    lines_text = [f"{n} nouvelle(s) offre(s) détectée(s) :", ""]
    lines_html = [
        "<p><strong>",
        f"{n} nouvelle(s) offre(s) détectée(s) sur Welcome to the Jungle",
        "</strong></p><ul>",
    ]
    for j in new_jobs:
        bits = [j["contract"], j["cities"], j["remote"]]
        meta = " · ".join(b for b in bits if b)
        lines_text.append(f"• {j['title']}")
        if meta:
            lines_text.append(f"  {meta}")
        if j["published_at"]:
            lines_text.append(f"  publié le {j['published_at'][:10]}")
        lines_text.append(f"  {j['url']}")
        lines_text.append("")

        meta_html = f" <em>({meta})</em>" if meta else ""
        pub_html = (
            f" — <span style='color:#666'>{j['published_at'][:10]}</span>"
            if j["published_at"]
            else ""
        )
        lines_html.append(
            f"<li><a href=\"{j['url']}\">{j['title']}</a>{meta_html}{pub_html}</li>"
        )
    lines_html.append("</ul>")
    lines_html.append(
        f"<p style='color:#888;font-size:12px'>Source&nbsp;: "
        f"<a href='https://www.welcometothejungle.com/fr/companies/{ORG_SLUG_PUBLIC}/jobs'>"
        f"welcometothejungle.com/fr/companies/{ORG_SLUG_PUBLIC}/jobs</a></p>"
    )

    return subject, "\n".join(lines_text), "".join(lines_html)


def send_email(subject: str, body_text: str, body_html: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    mail_from = os.environ.get("MAIL_FROM", user)
    mail_to = [a.strip() for a in os.environ["MAIL_TO"].split(",") if a.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.ehlo()
            s.login(user, password)
            s.send_message(msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="No state write, no email.")
    ap.add_argument("--seed", action="store_true", help="Write state.json and exit.")
    args = ap.parse_args()

    try:
        hits = fetch_jobs()
    except urllib.error.HTTPError as e:
        print(f"Algolia HTTP {e.code}: {e.read()[:300]!r}", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"Algolia network error: {e}", file=sys.stderr)
        return 2

    jobs = [summarize(h) for h in hits if h.get("reference")]
    current_refs = {j["ref"] for j in jobs}
    print(f"Fetched {len(jobs)} job(s) from WTJ.")

    if args.seed:
        save_state(current_refs)
        print(f"Seeded state.json with {len(current_refs)} ref(s).")
        return 0

    known = load_state()
    if known is None:
        # First run ever: seed silently, do not spam the inbox.
        if not args.dry_run:
            save_state(current_refs)
        print(
            f"First run: seeded state with {len(current_refs)} ref(s); "
            "no email sent."
        )
        return 0

    new_jobs = [j for j in jobs if j["ref"] not in known]
    if not new_jobs:
        print("No new jobs.")
        # Still persist state so disappeared refs don't keep re-surfacing
        # if they re-appear later.
        if not args.dry_run:
            save_state(current_refs)
        return 0

    print(f"{len(new_jobs)} new job(s):")
    for j in new_jobs:
        print(f"  - {j['ref']} {j['title']} -> {j['url']}")

    subject, text, html = render_email(new_jobs)
    if args.dry_run:
        print("\n--- DRY RUN EMAIL ---")
        print(f"Subject: {subject}\n")
        print(text)
        return 0

    send_email(subject, text, html)
    print(f"Sent email to {os.environ.get('MAIL_TO')}.")
    save_state(current_refs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
