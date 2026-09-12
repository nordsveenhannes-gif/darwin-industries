from __future__ import annotations

import argparse

from backend.storage import connect, init_db, now_iso


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record explicit customer authorization to launch an approved website."
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--approve-launch", action="store_true")
    args = parser.parse_args()

    if not args.approve_launch:
        raise SystemExit("Nothing changed. Supply --approve-launch to authorize launch.")

    conn = connect()
    init_db(conn)
    project = conn.execute(
        "SELECT * FROM website_projects WHERE id=?", (args.project_id,)
    ).fetchone()
    if not project:
        raise SystemExit(f"Website project #{args.project_id} does not exist.")
    if project["mode"] != "CUSTOMER":
        raise SystemExit("Demo projects cannot be authorized for a real public launch.")
    if project["status"] not in {"STAGING_APPROVED", "LAUNCH_INPUT_NEEDED"}:
        raise SystemExit(
            f"Project is {project['status']}; staging must be explicitly approved first."
        )

    missing = []
    if project["customer_approval_status"] != "APPROVED":
        missing.append("staging approval")
    if not project["payment_verified"]:
        missing.append("verified payment")
    if not project["asset_rights_confirmed"]:
        missing.append("confirmed production asset rights")

    unanswered = conn.execute(
        """SELECT COUNT(*) AS n
        FROM website_client_questions
        WHERE project_id=? AND required_for='LAUNCH' AND status!='ANSWERED'""",
        (args.project_id,),
    ).fetchone()["n"]
    if unanswered:
        missing.append(f"{int(unanswered)} unanswered launch questionnaire item(s)")

    if missing:
        conn.close()
        raise SystemExit("Launch authorization blocked by: " + ", ".join(missing) + ".")

    conn.execute(
        """UPDATE website_projects
        SET launch_approved=1,status='RELEASE_READY',updated_at=?
        WHERE id=?""",
        (now_iso(), args.project_id),
    )
    conn.execute(
        """INSERT INTO website_project_events(project_id,agent,stage,detail,created_at)
        VALUES(?,?,?,?,?)""",
        (
            args.project_id,
            "Customer",
            "LAUNCH_APPROVED",
            "Customer explicitly authorized launch after staging approval and production gates. No deployment was performed by this command.",
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()

    print(f"\nWebsite project #{args.project_id}: RELEASE READY")
    print("Explicit launch approval recorded.")
    print("No DNS change or production deployment was performed by this command.")


if __name__ == "__main__":
    main()
