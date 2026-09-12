import argparse
import os
from dotenv import load_dotenv
from agents import Runner

from backend.agents.atlas import build_atlas
from backend.agents.forge import build_forge
from backend.agents.ledger import build_ledger
from backend.agents.mercury import build_mercury
from backend.agents.sentinel import build_sentinel
from backend.storage import (
    claim_next_internal_task,
    complete_task,
    connect,
    fail_or_retry_task,
    init_db,
    latest_report,
    refresh_run_status,
    save_event,
)


AGENT_BUILDERS = {
    "Forge": build_forge,
    "Mercury": build_mercury,
    "Ledger": build_ledger,
    "Sentinel": build_sentinel,
}


def run_agent(agent, prompt: str) -> str:
    result = Runner.run_sync(agent, prompt)
    return result.final_output


def get_latest_runnable_run(conn):
    return conn.execute(
        """
        SELECT * FROM runs
        WHERE status IN ('READY_INTERNAL', 'WORKING_INTERNAL', 'INTERNAL_BLOCKED')
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def execute_one(conn, run) -> bool:
    task = claim_next_internal_task(conn, run["id"])
    if not task:
        status = refresh_run_status(conn, run["id"])
        print(f"No READY zero-cash internal tasks remain. Run status: {status}")
        return False

    # Hard safety gate: this worker can never execute external/cash tasks.
    if task["external_action"] or float(task["cash_budget_usd"]) != 0:
        raise RuntimeError("Worker safety gate blocked a non-internal or funded task.")

    owner = task["owner"]
    builder = AGENT_BUILDERS.get(owner)
    if not builder:
        next_status = fail_or_retry_task(
            conn,
            task["id"],
            "",
            "STATUS: FLAG\nREASONS:\n- No worker registered for task owner.",
            f"No agent builder for {owner}",
        )
        print(f"Task #{task['id']} could not run. Status: {next_status}")
        return True

    atlas_context = latest_report(conn, run["id"], "Atlas")
    prompt = f"""
You are executing ONE approved internal Darwin Industries task.

TASK ID: {task['id']}
OWNER: {owner}
TASK: {task['title']}

COMPANY OPPORTUNITY:
{run['opportunity']}

ATLAS CEO PLAN:
{atlas_context}

STRICT EXECUTION RULES:
- This is INTERNAL preparation only.
- Do not contact prospects or any external person.
- Do not spend money.
- Do not claim that outreach, payment, revenue, or customer activity occurred.
- Produce the actual useful work product for this task, not a plan to do it later.
- Keep the result practical enough for another agent to use.

Return only the completed work product.
"""

    print(f"\nExecuting task #{task['id']} — {owner}: {task['title']}")
    save_event(
        conn,
        run["id"],
        "TASK_STARTED",
        f"Task #{task['id']} started by {owner}.",
    )

    try:
        result_text = run_agent(builder(), prompt)

        if owner == "Sentinel":
            reviewer = build_atlas()
            review_role = "Atlas"
            qa_prompt = f"""
You are Atlas acting as a final internal reviewer.

Review the completed task below.

TASK:
{task['title']}

RESULT:
{result_text}

Return exactly:
STATUS: PASS
or
STATUS: FLAG

Then:
REASONS:
- concise bullets

REQUIRED_CHANGES:
- concise bullets, or "None"

Pass only if the work is useful, truthful, within zero-cash internal scope,
and does not claim external activity occurred.
"""
        else:
            reviewer = build_sentinel()
            review_role = "Sentinel"
            qa_prompt = f"""
Audit this completed internal Darwin Industries task.

TASK:
{task['title']}

OWNER:
{owner}

RESULT:
{result_text}

The task was authorized only for internal preparation with:
- zero cash spend,
- no outreach,
- no payment collection,
- no external actions.

Return exactly:
STATUS: PASS
or
STATUS: FLAG

Then:
REASONS:
- concise bullets

REQUIRED_CHANGES:
- concise bullets, or "None"
"""

        qa_report = run_agent(reviewer, qa_prompt)
        passed = "STATUS: PASS" in qa_report.upper()

        if passed:
            complete_task(conn, task["id"], result_text, qa_report)
            save_event(
                conn,
                run["id"],
                "TASK_COMPLETED",
                f"Task #{task['id']} completed and passed {review_role} QA.",
            )
            print(f"PASS — task #{task['id']} saved.")
        else:
            next_status = fail_or_retry_task(
                conn, task["id"], result_text, qa_report
            )
            save_event(
                conn,
                run["id"],
                "TASK_QA_FAILED",
                f"Task #{task['id']} failed QA and moved to {next_status}.",
            )
            print(f"FLAG — task #{task['id']} moved to {next_status}.")

    except Exception as exc:
        next_status = fail_or_retry_task(
            conn,
            task["id"],
            "",
            "STATUS: FLAG\nREASONS:\n- Worker execution raised an exception.",
            str(exc),
        )
        save_event(
            conn,
            run["id"],
            "TASK_ERROR",
            f"Task #{task['id']} errored and moved to {next_status}: {exc}",
        )
        print(f"ERROR — task #{task['id']} moved to {next_status}: {exc}")

    status = refresh_run_status(conn, run["id"])
    print(f"Run status: {status}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Darwin zero-cash internal autonomous worker."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process multiple READY internal tasks in this invocation.",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=6,
        help="Safety cap when --all is used. Default: 6.",
    )
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing from .env")

    conn = connect()
    init_db(conn)
    run = get_latest_runnable_run(conn)

    if not run:
        print("No runnable internal Darwin run found.")
        return

    limit = max(1, min(args.max_tasks, 20)) if args.all else 1
    completed = 0

    while completed < limit:
        if not execute_one(conn, run):
            break
        completed += 1

    print(f"\nWorker finished after {completed} task(s).")
    print("Check state with: python -m backend.status")


if __name__ == "__main__":
    main()
