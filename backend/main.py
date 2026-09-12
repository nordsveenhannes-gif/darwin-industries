import os
from dotenv import load_dotenv
from agents import Runner

from backend.agents.atlas import build_atlas
from backend.agents.mercury import build_mercury
from backend.agents.forge import build_forge
from backend.agents.ledger import build_ledger


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

    print("\n=== MERCURY / SALES ===\n")
    mercury_report = run_agent(build_mercury(), opportunity)
    print(mercury_report)

    print("\n=== FORGE / PRODUCT ===\n")
    forge_report = run_agent(build_forge(), opportunity)
    print(forge_report)

    print("\n=== LEDGER / FINANCE ===\n")
    ledger_report = run_agent(build_ledger(), opportunity)
    print(ledger_report)

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


if __name__ == "__main__":
    main()
