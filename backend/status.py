from backend.storage import connect, init_db


def main() -> None:
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
        print("\nTASK QUEUE")

        tasks = conn.execute(
            "SELECT * FROM tasks WHERE run_id=? ORDER BY id",
            (run["id"],),
        ).fetchall()

        if not tasks:
            print("  No tasks queued.")
        else:
            for task in tasks:
                external = "EXTERNAL" if task["external_action"] else "INTERNAL"
                print(
                    f"  #{task['id']} [{task['status']}] "
                    f"{task['owner']}: {task['title']} "
                    f"| {external} | cash cap USD {task['cash_budget_usd']:.2f} "
                    f"| attempts {task['attempts']}/{task['max_attempts']}"
                )
    else:
        print("No Darwin runs found yet.")

    pipeline = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='RESEARCHED' THEN 1 ELSE 0 END) AS researched,
            SUM(CASE WHEN status='SCORED' THEN 1 ELSE 0 END) AS scored,
            SUM(CASE WHEN status='AUDITED' THEN 1 ELSE 0 END) AS audited,
            SUM(CASE WHEN status='DRAFT_READY' THEN 1 ELSE 0 END) AS draft_ready
        FROM prospects
        """
    ).fetchone()

    print("\nSALES PIPELINE")
    print(f"  Total prospects: {pipeline['total'] or 0}")
    print(f"  Researched: {pipeline['researched'] or 0}")
    print(f"  Scored: {pipeline['scored'] or 0}")
    print(f"  Audited: {pipeline['audited'] or 0}")
    print(f"  Outreach drafts ready: {pipeline['draft_ready'] or 0}")

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

    print("\nEmail sending: DISABLED")
    print("Cash spending: DISABLED")
    print("No model calls were used to render this status screen.")


if __name__ == "__main__":
    main()
