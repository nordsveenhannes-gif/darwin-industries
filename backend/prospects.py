import json

from backend.storage import connect, init_db


def main() -> None:
    conn = connect()
    init_db(conn)

    prospects = conn.execute(
        """
        SELECT * FROM prospects
        ORDER BY
            CASE status
                WHEN 'DRAFT_READY' THEN 0
                WHEN 'AUDITED' THEN 1
                WHEN 'SCORED' THEN 2
                WHEN 'RESEARCHED' THEN 3
                ELSE 4
            END,
            COALESCE(sales_score, confidence) DESC,
            id DESC
        LIMIT 50
        """
    ).fetchall()

    print("\n=== DARWIN SALES PIPELINE ===\n")

    if not prospects:
        print("No researched prospects saved yet.")
        return

    for p in prospects:
        score = p["sales_score"]
        score_text = f"sales {score}/100" if score is not None else "not scored"
        print(
            f"#{p['id']} [{p['status']}] {p['business_name']} "
            f"| research {p['confidence']}% | {score_text}"
        )
        print(f"  Market: {p['city']} | {p['category']}")
        print(f"  Website: {p['website_url']}")
        print(f"  Observation: {p['observed_issue']}")
        if p["sales_reason"]:
            print(f"  Mercury: {p['sales_reason']}")
        if p["recommended_angle"]:
            print(f"  Angle: {p['recommended_angle']}")
        try:
            urls = json.loads(p["source_urls_json"])
        except Exception:
            urls = []
        if urls:
            print("  Sources:")
            for url in urls[:3]:
                print(f"    - {url}")
        if p["audit_text"]:
            print("  Audit: saved")
        if p["outreach_subject"]:
            print(f"  Draft subject: {p['outreach_subject']}")
        if p["outreach_body"]:
            print("  Draft email:")
            for line in p["outreach_body"].splitlines():
                print(f"    {line}")
        print()

    print("No model calls were used to display this pipeline.")


if __name__ == "__main__":
    main()
