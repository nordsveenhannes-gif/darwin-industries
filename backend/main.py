import os
from dotenv import load_dotenv
from agents import Runner

from backend.agents.atlas import build_atlas
from backend.agents.mercury import build_mercury
from backend.agents.forge import build_forge
from backend.agents.ledger import build_ledger
from backend.agents.sentinel import build_sentinel
from backend.storage import (
    connect,
    create_run,
    init_db,
    save_event,
    save_report,
    seed_validation_tasks,
    set_run_status,
)


def run_agent(agent, prompt: str) -> str:
    result = Runner.run_sync(agent, prompt)
    return result.final_output


def main() -> None:
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is missing. Copy .env.example to .env and add your key locally."
        )

    opportunity = (
        "Darwin Industries is evaluating a productized AI-assisted website audit "
        "for small local service businesses. The proposed deliverable covers mobile usability, "
        "offer clarity, contact friction, basic local SEO issues, and three prioritized improvements. "
        "The immediate goal is to validate demand within 48 hours with minimal upfront cost."
    )

    conn = connect()
    init_db(conn)
    run_id = create_run(conn, opportunity)
    save_event(conn, run_id, "RUN_STARTED", "Company planning run started.")

    print(f"\nDarwin run #{run_id} started. Reports will be saved to data/darwin.db.")

    print("\n=== MERCURY / SALES ===\n")
    mercury_report = run_agent(build_mercury(), opportunity)
    print(mercury_report)
    save_report(conn, run_id, "Mercury", mercury_report)

    print("\n=== FORGE / PRODUCT ===\n")
    forge_report = run_agent(build_forge(), opportunity)
    print(forge_report)
    save_report(conn, run_id, "Forge", forge_report)

    print("\n=== LEDGER / FINANCE ===\n")
    ledger_report = run_agent(build_ledger(), opportunity)
    print(ledger_report)
    save_report(conn, run_id, "Ledger", ledger_report)

    atlas_prompt = f"""
Darwin Industries is deciding whether to run a 48-hour validation experiment.

Proposed opportunity:
{opportunity}

Mercury's sales report:
{mercury_report}

Forge's fulfillment report:
{forge_report}

Ledger's finance report:
{ledger_report}

Act as CEO. Synthesize these department reports into ONE decision.
Return:
1. GO / MODIFY / STOP,
2. exact offer to test,
3. target customer,
4. starting price hypothesis,
5. first 48-hour task list by department,
6. success threshold,
7. stop condition,
8. maximum cash spend allowed for this experiment.
Do not invent completed outreach, customers, payments, or revenue.
"""

    print("\n=== ATLAS / CEO DECISION ===\n")
    atlas_report = run_agent(build_atlas(), atlas_prompt)
    print(atlas_report)
    save_report(conn, run_id, "Atlas", atlas_report)

    sentinel_prompt = f"""
Audit this proposed Darwin Industries experiment.

OPPORTUNITY:
{opportunity}

MERCURY:
{mercury_report}

FORGE:
{forge_report}

LEDGER:
{ledger_report}

ATLAS:
{atlas_report}

Important current control:
External outreach, spending, payment collection, and financial transactions are still disabled.
This run may only create internal preparation tasks.
"""

    print("\n=== SENTINEL / QA ===\n")
    sentinel_report = run_agent(build_sentinel(), sentinel_prompt)
    print(sentinel_report)
    save_report(conn, run_id, "Sentinel", sentinel_report)

    if "STATUS: PASS" in sentinel_report.upper():
        seed_validation_tasks(conn, run_id)
        set_run_status(conn, run_id, "READY_INTERNAL")
        save_event(
            conn,
            run_id,
            "QA_PASSED",
            "Sentinel passed the plan. Internal zero-cash tasks were queued.",
        )
        print("\nSentinel passed the plan. Internal tasks are now queued.")
    else:
        set_run_status(conn, run_id, "BLOCKED_QA")
        save_event(
            conn,
            run_id,
            "QA_BLOCKED",
            "Sentinel flagged the plan. No tasks were queued.",
        )
        print("\nSentinel flagged the plan. Execution remains blocked.")

    print("\nView saved company state without using any model tokens:")
    print("python -m backend.status")


if __name__ == "__main__":
    main()
