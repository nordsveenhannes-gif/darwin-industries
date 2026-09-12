import argparse
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import resend
from dotenv import load_dotenv

from backend.storage import connect, init_db, latest_run_id, now_iso, save_event


ROLE_PREFIXES = {
    "admin",
    "booking",
    "bookings",
    "contact",
    "hello",
    "info",
    "kontakt",
    "kundservice",
    "mail",
    "office",
    "post",
    "reception",
    "sales",
    "service",
    "support",
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def email_sending_enabled() -> bool:
    return _env_bool("DARWIN_ALLOW_EMAIL_SEND", False)


def daily_send_cap() -> int:
    try:
        value = int(os.getenv("DARWIN_EMAIL_DAILY_CAP", "3"))
    except ValueError:
        value = 3
    return max(1, min(value, 10))


def minimum_sales_score() -> int:
    try:
        value = int(os.getenv("DARWIN_EMAIL_MIN_SALES_SCORE", "70"))
    except ValueError:
        value = 70
    return max(0, min(value, 100))


def _website_host(website_url: str) -> str:
    parsed = urlparse(website_url if "://" in website_url else "https://" + website_url)
    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def is_safe_business_email(email: str | None, website_url: str) -> bool:
    if not email:
        return False
    candidate = email.strip().lower()
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_~-]+@[a-z0-9.-]+\.[a-z]{2,}", candidate):
        return False

    local, domain = candidate.rsplit("@", 1)
    local_root = re.split(r"[+._-]", local, maxsplit=1)[0]
    if local_root not in ROLE_PREFIXES:
        return False

    host = _website_host(website_url)
    if not host:
        return False

    return (
        domain == host
        or host.endswith("." + domain)
        or domain.endswith("." + host)
    )


def suppress_email(conn, email: str, reason: str = "owner suppression") -> None:
    conn.execute(
        """
        INSERT INTO suppressions(email, reason, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET reason=excluded.reason
        """,
        (email.strip().lower(), reason, now_iso()),
    )
    conn.commit()


def _is_suppressed(conn, email: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM suppressions WHERE email=? LIMIT 1",
        (email.strip().lower(),),
    ).fetchone()
    return row is not None


def _sent_today(conn) -> int:
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM outbound_emails
        WHERE status='SENT'
          AND sent_at >= ?
        """,
        (start,),
    ).fetchone()
    return int(row["n"] or 0)


def _ensure_opt_out(body: str) -> str:
    lower = body.lower()
    if "opt out" in lower or "no thanks" in lower or "not hear from" in lower:
        return body.strip()
    return (
        body.strip()
        + "\n\nIf you'd rather not hear from us again, just reply \"no thanks\"."
    )


def _response_id(response) -> str | None:
    if isinstance(response, dict):
        value = response.get("id")
        return str(value) if value else None
    value = getattr(response, "id", None)
    return str(value) if value else None


def ready_outreach_rows(conn, limit: int = 10):
    return conn.execute(
        """
        SELECT *
        FROM prospects
        WHERE status='CONTACT_READY'
          AND contact_email IS NOT NULL
          AND outreach_subject IS NOT NULL
          AND outreach_body IS NOT NULL
          AND outreach_qa LIKE '%STATUS: PASS%'
          AND COALESCE(sales_score, 0) >= ?
        ORDER BY sales_score DESC, confidence DESC, id ASC
        LIMIT ?
        """,
        (minimum_sales_score(), max(1, min(limit, 25))),
    ).fetchall()


def send_ready_outreach(conn, run_id: int | None, limit: int = 1) -> tuple[int, int]:
    if not email_sending_enabled():
        return 0, 0

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("DARWIN_EMAIL_FROM", "").strip()
    reply_to = os.getenv("DARWIN_EMAIL_REPLY_TO", "").strip()

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is required when email sending is enabled.")
    if not from_email:
        raise RuntimeError("DARWIN_EMAIL_FROM is required when email sending is enabled.")
    if not reply_to:
        raise RuntimeError("DARWIN_EMAIL_REPLY_TO is required when email sending is enabled.")

    remaining = max(0, daily_send_cap() - _sent_today(conn))
    if remaining <= 0:
        return 0, 0

    resend.api_key = api_key
    sent = 0
    skipped = 0

    for row in ready_outreach_rows(conn, min(limit, remaining)):
        recipient = row["contact_email"].strip().lower()

        if _is_suppressed(conn, recipient):
            conn.execute(
                "UPDATE prospects SET status='CONTACT_SUPPRESSED', updated_at=? WHERE id=?",
                (now_iso(), row["id"]),
            )
            conn.commit()
            skipped += 1
            continue

        prior = conn.execute(
            """
            SELECT 1 FROM outbound_emails
            WHERE to_email=? AND status='SENT'
            LIMIT 1
            """,
            (recipient,),
        ).fetchone()
        if prior:
            conn.execute(
                "UPDATE prospects SET status='ALREADY_CONTACTED', updated_at=? WHERE id=?",
                (now_iso(), row["id"]),
            )
            conn.commit()
            skipped += 1
            continue

        body = _ensure_opt_out(row["outreach_body"])
        cur = conn.execute(
            """
            INSERT INTO outbound_emails(
                prospect_id, provider, from_email, to_email, subject,
                body_text, status, created_at
            )
            VALUES (?, 'resend', ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                row["id"],
                from_email,
                recipient,
                row["outreach_subject"],
                body,
                now_iso(),
            ),
        )
        email_id = int(cur.lastrowid)
        conn.commit()

        try:
            params: resend.Emails.SendParams = {
                "from": from_email,
                "to": [recipient],
                "subject": row["outreach_subject"],
                "text": body,
                "reply_to": reply_to,
                "tags": [
                    {"name": "source", "value": "darwin"},
                    {"name": "prospect_id", "value": str(row["id"])},
                ],
            }
            response = resend.Emails.send(params)
            provider_id = _response_id(response)

            conn.execute(
                """
                UPDATE outbound_emails
                SET status='SENT', provider_message_id=?, sent_at=?
                WHERE id=?
                """,
                (provider_id, now_iso(), email_id),
            )
            conn.execute(
                """
                UPDATE prospects
                SET status='OUTREACH_SENT', updated_at=?
                WHERE id=?
                """,
                (now_iso(), row["id"]),
            )
            conn.commit()
            sent += 1

            if run_id is not None:
                save_event(
                    conn,
                    run_id,
                    "OUTREACH_SENT",
                    f"Controlled outreach sent for prospect #{row['id']} via Resend.",
                )

        except Exception as exc:
            conn.execute(
                """
                UPDATE outbound_emails
                SET status='FAILED', last_error=?
                WHERE id=?
                """,
                (str(exc)[:1000], email_id),
            )
            conn.execute(
                """
                UPDATE prospects
                SET status='SEND_FAILED_REVIEW', updated_at=?
                WHERE id=?
                """,
                (now_iso(), row["id"]),
            )
            conn.commit()

            if run_id is not None:
                save_event(
                    conn,
                    run_id,
                    "OUTREACH_SEND_FAILED",
                    f"Prospect #{row['id']} send failed and was stopped for review.",
                )

    return sent, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Darwin controlled outbound email.")
    parser.add_argument(
        "--send-ready",
        action="store_true",
        help="Send eligible CONTACT_READY emails, subject to all guardrails.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum emails for this invocation (daily cap still applies).",
    )
    parser.add_argument(
        "--suppress",
        help="Add an address to the permanent local suppression list.",
    )
    parser.add_argument(
        "--reason",
        default="owner suppression",
        help="Suppression reason.",
    )
    args = parser.parse_args()

    load_dotenv()
    conn = connect()
    init_db(conn)

    if args.suppress:
        suppress_email(conn, args.suppress, args.reason)
        print(f"Suppressed: {args.suppress}")
        return

    rows = ready_outreach_rows(conn, limit=max(1, args.limit))
    print("\n=== DARWIN OUTBOUND EMAIL ===")
    print(f"Sending enabled: {'YES' if email_sending_enabled() else 'NO'}")
    print(f"Daily cap: {daily_send_cap()}")
    print(f"Sent today: {_sent_today(conn)}")
    print(f"Eligible ready emails visible: {len(rows)}")

    if not args.send_ready:
        print("Dry run only. Add --send-ready to execute controlled sends.")
        return

    sent, skipped = send_ready_outreach(
        conn,
        run_id=latest_run_id(conn),
        limit=max(1, args.limit),
    )
    print(f"Sent: {sent}; skipped: {skipped}")


if __name__ == "__main__":
    main()
