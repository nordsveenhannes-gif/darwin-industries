from __future__ import annotations

import argparse

from backend.client_intake import collect_client_answers
from backend.storage import connect, init_db, now_iso


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect launch-only website information from the customer."
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()

    conn = connect()
    init_db(conn)
    project = conn.execute(
        "SELECT * FROM website_projects WHERE id=?", (args.project_id,)
    ).fetchone()
    if not project:
        raise SystemExit(f"Website project #{args.project_id} does not exist.")
    if project["status"] not in {"STAGING_READY", "STAGING_APPROVED", "LAUNCH_INPUT_NEEDED"}:
        raise SystemExit(
            f"Project is {project['status']}; launch intake belongs after a validated staging build."
        )

    rows = conn.execute(
        """
        SELECT question_key,question,why_needed,required_for,status,answer
        FROM website_client_questions
        WHERE project_id=? AND required_for='LAUNCH'
        ORDER BY id
        """,
        (args.project_id,),
    ).fetchall()
    questions = [
        {
            "key": row["question_key"],
            "question": row["question"],
            "why": row["why_needed"],
            "required_for": row["required_for"],
            "placeholder": row["answer"] or "Provide the production-ready answer or note what still needs to be supplied.",
        }
        for row in rows
        if row["status"] != "ANSWERED"
    ]

    if not questions:
        print("All launch questionnaire items are already answered.")
        conn.close()
        return

    conn.execute(
        "UPDATE website_projects SET status='LAUNCH_INPUT_NEEDED',updated_at=? WHERE id=?",
        (now_iso(), args.project_id),
    )
    conn.execute(
        """INSERT INTO website_project_events(project_id,agent,stage,detail,created_at)
        VALUES(?,?,?,?,?)""",
        (
            args.project_id,
            "Mercury",
            "LAUNCH_INTAKE_REQUESTED",
            f"Customer was asked {len(questions)} launch-only production question(s).",
            now_iso(),
        ),
    )
    conn.commit()
    business_name = project["business_name"]
    conn.close()

    answers = collect_client_answers(
        args.project_id,
        business_name,
        questions=questions,
        port=args.port,
        heading="Before launch, we need the production details.",
        open_browser=True,
    )

    conn = connect()
    init_db(conn)
    conn.execute(
        """UPDATE website_projects
        SET status=CASE
            WHEN customer_approval_status='APPROVED' THEN 'STAGING_APPROVED'
            ELSE 'STAGING_READY'
        END,
        updated_at=?
        WHERE id=?""",
        (now_iso(), args.project_id),
    )
    conn.execute(
        """INSERT INTO website_project_events(project_id,agent,stage,detail,created_at)
        VALUES(?,?,?,?,?)""",
        (
            args.project_id,
            "Customer",
            "LAUNCH_INTAKE_COMPLETE",
            f"Customer answered {len(answers)} launch-only production question(s).",
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()

    print("\nLaunch questionnaire complete.")
    print("This did not publish the website or authorize a launch.")


if __name__ == "__main__":
    main()
