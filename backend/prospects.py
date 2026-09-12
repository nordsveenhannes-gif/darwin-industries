import json

from backend.storage import connect, init_db


def main() -> None:
    conn = connect()
    init_db(conn)

    prospects = conn.execute(
        """
        SELECT * FROM prospects
        ORDER BY confidence DESC, id DESC
        LIMIT 50
        """
    ).fetchall()

    print("\n=== DARWIN RESEARCHED PROSPECTS ===\n")

    if not prospects:
        print("No researched prospects saved yet.")
        return

    for p in prospects:
        print(f"#{p['id']} [{p['confidence']}%] {p['business_name']}")
        print(f"  Market: {p['city']} | {p['category']}")
        print(f"  Website: {p['website_url']}")
        print(f"  Observation: {p['observed_issue']}")
        print(f"  Why fit: {p['why_fit']}")
        try:
            urls = json.loads(p["source_urls_json"])
        except Exception:
            urls = []
        if urls:
            print("  Sources:")
            for url in urls[:4]:
                print(f"    - {url}")
        print(f"  Status: {p['status']}")
        print()

    print("No model calls were used to display this list.")


if __name__ == "__main__":
    main()
