import argparse
import os
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

from backend.emailer import daily_send_cap, email_sending_enabled, send_ready_outreach
from backend.pipeline import (
    audit_best_prospect,
    draft_outreach_for_best,
    find_public_contact_for_best,
    score_researched_prospects,
)
from backend.research import research_batch
from backend.storage import (
    connect,
    init_db,
    latest_run_id,
    save_event,
    start_work_session,
    update_work_session,
)


DEFAULT_MARKETS = [
    "Stockholm, Sweden",
    "Gothenburg, Sweden",
    "Oslo, Norway",
]
DEFAULT_CATEGORIES = [
    "plumbers",
    "electricians",
    "roofers",
]


def _list_env(name: str, fallback: list[str]) -> list[str]:
    value = os.getenv(name, "").strip()
    if not value:
        return fallback
    separator = ";" if ";" in value else ","
    items = [item.strip() for item in value.split(separator) if item.strip()]
    return items or fallback


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Darwin Industries as a bounded autonomous workday."
    )
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--cycle-minutes", type=int, default=60)
    parser.add_argument("--max-model-calls", type=int, default=42)
    parser.add_argument("--prospects-per-cycle", type=int, default=4)
    args = parser.parse_args()

    hours = max(0.25, min(args.hours, 12.0))
    cycle_minutes = max(10, min(args.cycle_minutes, 180))
    max_calls = max(5, min(args.max_model_calls, 100))
    prospects_per_cycle = max(1, min(args.prospects_per_cycle, 8))

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing from .env")

    markets = _list_env("DARWIN_MARKETS", DEFAULT_MARKETS)
    categories = _list_env("DARWIN_CATEGORIES", DEFAULT_CATEGORIES)

    conn = connect()
    init_db(conn)
    run_id = latest_run_id(conn)
    session_id = start_work_session(conn, hours, max_calls)

    deadline = datetime.now() + timedelta(hours=hours)
    cycles = 0
    calls_used = 0
    index = 0
    budget_idle_announced = False
    sending = email_sending_enabled()

    print("\n=== DARWIN WORKDAY STARTED ===")
    print(f"Target duration: {hours:g} hour(s)")
    print(f"Cycle interval: {cycle_minutes} minute(s)")
    print(f"Model-call guardrail: {max_calls}")
    print(
        "Controlled email sending: "
        + (f"ENABLED (daily cap {daily_send_cap()})" if sending else "DISABLED")
    )
    print("Cash spending: DISABLED")
    print("Press Ctrl+C to stop safely.\n")

    try:
        while datetime.now() < deadline:
            # Worst-case model units per cycle:
            # research 1 + scoring 1 + audit/QA 2 + draft/QA 2 + contact verify 1 = 7.
            if calls_used + 7 > max_calls:
                remaining = max(0, int((deadline - datetime.now()).total_seconds() / 60))
                if not budget_idle_announced:
                    print(
                        f"API guardrail reached ({calls_used}/{max_calls}). "
                        f"Darwin will remain idle for the remaining ~{remaining} minute(s)."
                    )
                    if run_id is not None:
                        save_event(
                            conn,
                            run_id,
                            "WORKDAY_BUDGET_IDLE",
                            f"Model-call guardrail reached at {calls_used}/{max_calls}.",
                        )
                    budget_idle_announced = True
                sleep_seconds = min(
                    300,
                    max(1, int((deadline - datetime.now()).total_seconds())),
                )
                time.sleep(sleep_seconds)
                continue

            market = markets[index % len(markets)]
            category = categories[index % len(categories)]
            index += 1
            cycles += 1

            print(f"\n--- Cycle {cycles}: {category} in {market} ---")

            try:
                saved, duplicates, used = research_batch(
                    conn,
                    market=market,
                    category=category,
                    limit=prospects_per_cycle,
                    run_id=run_id,
                )
                calls_used += used
                print(f"Oracle: {saved} saved, {duplicates} duplicate(s).")

                scored, used = score_researched_prospects(
                    conn,
                    run_id=run_id,
                    limit=max(5, prospects_per_cycle),
                )
                calls_used += used
                print(f"Mercury: {scored} prospect(s) scored.")

                prospect_id, used = audit_best_prospect(conn, run_id=run_id)
                calls_used += used
                if prospect_id is not None:
                    print(f"Forge/Sentinel: prospect #{prospect_id} audit processed.")

                prospect_id, used = draft_outreach_for_best(conn, run_id=run_id)
                calls_used += used
                if prospect_id is not None:
                    print(
                        f"Mercury/Sentinel: prospect #{prospect_id} "
                        "outreach draft processed."
                    )

                prospect_id, used = find_public_contact_for_best(conn, run_id=run_id)
                calls_used += used
                if prospect_id is not None:
                    print(
                        f"Oracle: prospect #{prospect_id} public role contact checked."
                    )

                if sending:
                    sent, skipped = send_ready_outreach(
                        conn,
                        run_id=run_id,
                        limit=1,
                    )
                    if sent or skipped:
                        print(
                            f"Resend: {sent} controlled outreach sent; "
                            f"{skipped} skipped by guardrails."
                        )

                update_work_session(
                    conn,
                    session_id,
                    cycles_completed=cycles,
                    estimated_calls_used=calls_used,
                    note=f"Last cycle: {category} in {market}",
                )

            except Exception as exc:
                print(f"Cycle error: {exc}")
                if run_id is not None:
                    save_event(
                        conn,
                        run_id,
                        "WORKDAY_CYCLE_ERROR",
                        f"Cycle {cycles} error: {exc}",
                    )
                update_work_session(
                    conn,
                    session_id,
                    cycles_completed=cycles,
                    estimated_calls_used=calls_used,
                    note=f"Last error: {exc}",
                )

            if datetime.now() >= deadline:
                break

            seconds_until_next = min(
                cycle_minutes * 60,
                max(1, int((deadline - datetime.now()).total_seconds())),
            )
            next_time = datetime.now() + timedelta(seconds=seconds_until_next)
            print(
                f"Calls used: {calls_used}/{max_calls}. "
                f"Next cycle around {next_time.strftime('%H:%M')}."
            )
            time.sleep(seconds_until_next)

        update_work_session(
            conn,
            session_id,
            cycles_completed=cycles,
            estimated_calls_used=calls_used,
            status="COMPLETE",
            note="Bounded workday completed.",
            ended=True,
        )
        print("\n=== DARWIN WORKDAY COMPLETE ===")
        print(f"Cycles: {cycles}")
        print(f"Estimated model-call units used: {calls_used}/{max_calls}")

    except KeyboardInterrupt:
        update_work_session(
            conn,
            session_id,
            cycles_completed=cycles,
            estimated_calls_used=calls_used,
            status="STOPPED",
            note="Stopped by owner.",
            ended=True,
        )
        print("\nDarwin workday stopped safely.")

    print("Review pipeline with: python -m backend.prospects")


if __name__ == "__main__":
    main()
