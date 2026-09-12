from __future__ import annotations

import argparse

from backend.storage import connect, init_db, now_iso


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record customer staging approval for a Darwin website project."
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument(
        "--approve-staging",
        action="store_true",
        help="Record explicit customer approval of the current staging build.",
    )
    args = parser.parse_args()

    if not args.approve_staging:
        raise SystemExit("Nothing changed. Supply --approve-staging to record customer approval.")

    conn = connect()
    init_db(conn)
    project = conn.execute(
        "SELECT * FROM website_projects WHERE id=?", (args.project_id,)
    ).fetchone()
    if not project:
        raise SystemExit(f"Website project #{args.project_id} does not exist.")
    if project["status"] != "STAGING_READY":
        raise SystemExit(
            f"Project is {project['status']}; only a validated STAGING_READY build can be approved."
        )

    conn.execute(
        """UPDATE website_projects
        SET status='STAGING_APPROVED', customer_approval_status='APPROVED',
            launch_approved=0, updated_at=?
        WHERE id=?""",
        (now_iso(), args.project_id),
    )
    conn.execute(
        """INSERT INTO website_project_events(project_id,agent,stage,detail,created_at)
        VALUES(?,?,?,?,?)""",
        (
            args.project_id,
            "Customer",
            "STAGING_APPROVED",
            "Customer explicitly approved the current staging build. This does not itself publish the site.",
            now_iso(),
        ),
    )
    conn.commit()

    project = conn.execute(
        "SELECT * FROM website_projects WHERE id=?", (args.project_id,)
    ).fetchone()
    launch_rows = conn.execute(
        """SELECT status FROM website_client_questions
        WHERE project_id=? AND required_for='LAUNCH'""",
        (args.project_id,),
    ).fetchall()
    unanswered_launch = sum(1 for row in launch_rows if row["status"] != "ANSWERED")

    print(f"\nWebsite project #{args.project_id}: STAGING APPROVED")
    print("Public deployment was NOT performed.")
    print("Staging approval is intentionally separate from launch approval.")
    if project["mode"] == "DEMO":
        print("Demo project: approval is simulated and no payment/revenue is implied.")
    else:
        missing = []
        if not project["payment_verified"]:
            missing.append("verified payment")
        if not project["asset_rights_confirmed"]:
            missing.append("confirmed production asset rights")
        if unanswered_launch:
            missing.append(f"{unanswered_launch} unanswered launch questionnaire item(s)")
        if missing:
            print("Launch remains blocked by: " + ", ".join(missing) + ".")
        else:
            print("Commercial prerequisites appear complete; explicit launch approval is still required separately.")

    conn.close()


if __name__ == "__main__":
    main()
