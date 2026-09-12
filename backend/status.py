from backend.storage import connect, init_db


def main() -> None:
    conn = connect()
    init_db(conn)

    run = conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if not run:
        print("No Darwin runs found yet.")
        return

    print("\n=== DARWIN COMPANY STATUS ===\n")
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
                f"| {external} | cash cap ${task['cash_budget_usd']:.2f} "
                f"| attempts {task['attempts']}/{task['max_attempts']}"
            )

    print("\nNo model calls were used to render this status screen.")


if __name__ == "__main__":
    main()
