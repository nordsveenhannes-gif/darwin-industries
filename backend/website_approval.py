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
            launch_approved=1, updated_at=?
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
    real_launch_ready = bool(
        project["mode"] == "CUSTOMER"
        and project["launch_approved"]
        and project["payment_verified"]
        and project["asset_rights_confirmed"]
    )

    print(f"\nWebsite project #{args.project_id}: STAGING APPROVED")
    print("Public deployment was NOT performed.")
    if project["mode"] == "DEMO":
        print("Demo project: approval is simulated and no payment/revenue is implied.")
    elif real_launch_ready:
        print("Commercial gates recorded: staging approved, payment verified, asset rights confirmed.")
        print("Production deployment still requires a configured customer-owned hosting/domain target.")
    else:
        missing = []
        if not project["payment_verified"]:
            missing.append("verified payment")
        if not project["asset_rights_confirmed"]:
            missing.append("confirmed asset rights")
        if missing:
            print("Launch remains blocked by: " + ", ".join(missing) + ".")

    conn.close()


if __name__ == "__main__":
    main()
