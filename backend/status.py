import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from backend.emailer import daily_send_cap, email_sending_enabled
from backend.storage import connect, init_db


def main() -> None:
    load_dotenv()
    conn = connect()
    init_db(conn)

    run = conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
    ).fetchone()

    print("\n=== DARWIN COMPANY STATUS ===\n")

    if run:
        print(f"Run: #{run['id']}")
        print(f"Status: {run['status']}")
        print(f"Created: {run['created_at']}")
    else:
        print("No Darwin runs found yet.")

    agents = conn.execute(
        """
        SELECT agent, title, status, last_action, confidence, stress,
               motivation, job_security
        FROM agent_state
        ORDER BY CASE agent
            WHEN 'Atlas' THEN 1
            WHEN 'Mercury' THEN 2
            WHEN 'Forge' THEN 3
            WHEN 'Freya' THEN 4
            WHEN 'Nova' THEN 5
            WHEN 'Satoshi' THEN 6
            WHEN 'Midas' THEN 7
            WHEN 'Oracle' THEN 8
            WHEN 'Ledger' THEN 9
            WHEN 'Sentinel' THEN 10
            ELSE 99 END
        """
    ).fetchall()

    print("\nAGENT FLOOR")
    for agent in agents:
        print(
            f"  {agent['agent']:<9} [{agent['status']}] {agent['title']} "
            f"| confidence {agent['confidence']} | stress {agent['stress']} "
            f"| motivation {agent['motivation']} | job security {agent['job_security']}"
        )
        if agent["last_action"]:
            print(f"      {agent['last_action']}")

    shifts = conn.execute(
        """
        SELECT agent, COUNT(*) AS n, MAX(cycle) AS latest_cycle
        FROM department_reports
        GROUP BY agent
        ORDER BY MAX(id) DESC
        """
    ).fetchall()
    if shifts:
        print("\nDEPARTMENT WORK COMPLETED")
        for row in shifts:
            print(
                f"  {row['agent']}: {row['n']} report(s), "
                f"latest cycle {row['latest_cycle']}"
            )

    pipeline = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='RESEARCHED' THEN 1 ELSE 0 END) AS researched,
            SUM(CASE WHEN status='SCORED' THEN 1 ELSE 0 END) AS scored,
            SUM(CASE WHEN status='AUDITED' THEN 1 ELSE 0 END) AS audited,
            SUM(CASE WHEN status='DRAFT_READY' THEN 1 ELSE 0 END) AS draft_ready,
            SUM(CASE WHEN status='CONTACT_READY' THEN 1 ELSE 0 END) AS contact_ready,
            SUM(CASE WHEN status='OUTREACH_SENT' THEN 1 ELSE 0 END) AS sent,
            SUM(CASE WHEN status='CONTACT_UNAVAILABLE' THEN 1 ELSE 0 END) AS no_contact,
            SUM(CASE WHEN status='SEND_FAILED_REVIEW' THEN 1 ELSE 0 END) AS failed
        FROM prospects
        """
    ).fetchone()

    print("\nSALES PIPELINE")
    print(f"  Total prospects: {pipeline['total'] or 0}")
    print(f"  Researched: {pipeline['researched'] or 0}")
    print(f"  Scored: {pipeline['scored'] or 0}")
    print(f"  Audited: {pipeline['audited'] or 0}")
    print(f"  Outreach drafts ready: {pipeline['draft_ready'] or 0}")
    print(f"  Verified public role contacts: {pipeline['contact_ready'] or 0}")
    print(f"  Outreach sent: {pipeline['sent'] or 0}")
    print(f"  No safe public contact: {pipeline['no_contact'] or 0}")
    print(f"  Send failures held for review: {pipeline['failed'] or 0}")

    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    sent_today = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM outbound_emails
        WHERE status='SENT' AND sent_at >= ?
        """,
        (start,),
    ).fetchone()["n"]
    suppressed = conn.execute(
        "SELECT COUNT(*) AS n FROM suppressions"
    ).fetchone()["n"]

    session = conn.execute(
        "SELECT * FROM work_sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if session:
        print("\nLATEST WORKDAY")
        print(f"  Status: {session['status']}")
        print(f"  Cycles: {session['cycles_completed']}")
        print(
            f"  Model-call guardrail: "
            f"{session['estimated_calls_used']}/{session['model_call_budget']}"
        )
        print(f"  Started: {session['started_at']}")
        if session["ended_at"]:
            print(f"  Ended: {session['ended_at']}")

    print("\nOUTBOUND CONTROLS")
    print(
        "  Email sending: "
        + ("ENABLED" if email_sending_enabled() else "DISABLED")
    )
    print(f"  Daily cap: {daily_send_cap()}")
    print(f"  Sent today (UTC): {sent_today or 0}")
    print(f"  Suppressed addresses: {suppressed or 0}")
    print(f"  Sender configured: {'YES' if os.getenv('DARWIN_EMAIL_FROM') else 'NO'}")
    print(f"  Reply-to configured: {'YES' if os.getenv('DARWIN_EMAIL_REPLY_TO') else 'NO'}")
    print("  Cash spending: DISABLED")
    print("No model calls were used to render this status screen.")


if __name__ == "__main__":
    main()
