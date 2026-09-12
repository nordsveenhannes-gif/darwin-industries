import argparse

from backend.storage import connect, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Show a saved Darwin task.")
    parser.add_argument("task_id", type=int)
    args = parser.parse_args()

    conn = connect()
    init_db(conn)
    task = conn.execute(
        "SELECT * FROM tasks WHERE id=?",
        (args.task_id,),
    ).fetchone()

    if not task:
        raise SystemExit(f"Task #{args.task_id} not found.")

    print(f"\n=== TASK #{task['id']} ===")
    print(f"Owner: {task['owner']}")
    print(f"Title: {task['title']}")
    print(f"Status: {task['status']}")
    print(f"Attempts: {task['attempts']}/{task['max_attempts']}")

    print("\n=== RESULT ===\n")
    print(task["result_text"] or "(no result saved)")

    print("\n=== QA ===\n")
    print(task["qa_report"] or "(no QA report saved)")

    if task["last_error"]:
        print("\n=== LAST ERROR ===\n")
        print(task["last_error"])

    print("\nNo model calls were used to display this task.")


if __name__ == "__main__":
    main()
