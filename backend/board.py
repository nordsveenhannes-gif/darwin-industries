from backend.storage import connect, init_db


def main() -> None:
    conn = connect()
    init_db(conn)

    print("\n=== HOSKO'S SHADY SHENANIGANS — BOARD / DEPARTMENT REPORTS ===\n")

    agents = ["Atlas", "Ledger", "Nova", "Freya", "Midas", "Satoshi"]
    found = False

    for agent in agents:
        row = conn.execute(
            """
            SELECT *
            FROM department_reports
            WHERE agent=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (agent,),
        ).fetchone()

        if not row:
            print(f"{agent}: no department report yet.\n")
            continue

        found = True
        print(f"{agent} — {row['role']} — cycle {row['cycle']} [{row['status']}]")
        print("-" * 72)
        print(row["report"])
        print()

    if not found:
        print("No department shifts have completed yet.")

    print("No model calls were used to render this board view.")


if __name__ == "__main__":
    main()
