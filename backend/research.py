import argparse
import json
import os

from dotenv import load_dotenv
from agents import Runner

from backend.agents.oracle import ProspectBatch, build_oracle
from backend.storage import (
    connect,
    init_db,
    latest_run_id,
    save_event,
    save_prospect,
)


def research_batch(
    conn,
    market: str,
    category: str,
    limit: int = 5,
    run_id: int | None = None,
) -> tuple[int, int, int]:
    limit = max(1, min(limit, 15))
    if run_id is None:
        run_id = latest_run_id(conn)

    prompt = f"""
Find up to {limit} real candidate businesses for Darwin Industries.

MARKET:
{market}

CATEGORY:
{category}

GOAL:
Identify small/local service businesses whose public websites may benefit
from Darwin's productized website audit.

For each candidate:
- verify the business appears real and relevant to the requested market/category,
- provide its public website URL,
- give ONE careful, evidence-based website observation,
- explain briefly why it fits the pilot,
- include supporting public source URLs,
- assign confidence 0-100.

This is research only. Do not contact anyone and do not collect personal data.
"""

    result = Runner.run_sync(build_oracle(), prompt)
    batch = result.final_output

    if not isinstance(batch, ProspectBatch):
        raise RuntimeError("Oracle returned an unexpected output type.")

    saved = 0
    duplicates = 0

    for prospect in batch.prospects[:limit]:
        inserted = save_prospect(
            conn=conn,
            run_id=run_id,
            market=market,
            category=category,
            business_name=prospect.business_name,
            website_url=prospect.website_url,
            city=prospect.city,
            observed_issue=prospect.observed_issue,
            why_fit=prospect.why_fit,
            source_urls_json=json.dumps(prospect.source_urls),
            confidence=prospect.confidence,
        )
        if inserted:
            saved += 1
        else:
            duplicates += 1

    if run_id is not None:
        save_event(
            conn,
            run_id,
            "WEB_RESEARCH_COMPLETED",
            (
                f"Oracle researched market={market!r}, category={category!r}; "
                f"saved={saved}, duplicates={duplicates}."
            ),
        )

    # One hosted agent run is counted as one model-call unit for Darwin's local guardrail.
    return saved, duplicates, 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only live web research for Darwin Industries."
    )
    parser.add_argument(
        "--market",
        required=True,
        help='Target geography, e.g. "Stockholm, Sweden".',
    )
    parser.add_argument(
        "--category",
        required=True,
        help='Local-service category, e.g. "plumbers".',
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum candidates to request (1-15, default 8).",
    )
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing from .env")

    conn = connect()
    init_db(conn)

    print("\nOracle is performing read-only live web research...")
    saved, duplicates, _ = research_batch(
        conn,
        market=args.market,
        category=args.category,
        limit=args.limit,
    )

    print(f"\nSaved {saved} new prospect(s); skipped {duplicates} duplicate(s).")
    print("No outreach was sent.")
    print("View saved prospects with: python -m backend.prospects")


if __name__ == "__main__":
    main()
