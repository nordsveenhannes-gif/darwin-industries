import argparse
import os
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

from backend.company_shift import (
    end_shift,
    run_support_shift,
    set_core_agent_action,
    start_shift,
)
from backend.emailer import daily_send_cap, email_sending_enabled, send_ready_outreach
from backend.pipeline import (
    audit_best_prospect,
    draft_outreach_for_best,
    find_public_contact_for_best,
    score_researched_prospects,
)
from backend.research import research_batch
from backend.branding import INTERNAL_NAME
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
        description="Run Hosko’s Shady Shenanigans as a bounded autonomous workday."
    )
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--cycle-minutes", type=int, default=60)
    parser.add_argument("--max-model-calls", type=int, default=50)
    parser.add_argument("--prospects-per-cycle", type=int, default=4)
    args = parser.parse_args()

    hours = max(0.25, min(args.hours, 12.0))
    cycle_minutes = max(10, min(args.cycle_minutes, 180))
    max_calls = max(8, min(args.max_model_calls, 120))
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
    start_shift(conn)

    deadline = datetime.now() + timedelta(hours=hours)
    cycles = 0
    calls_used = 0
    index = 0
    budget_idle_announced = False
    sending = email_sending_enabled()

    print(f"\n=== {INTERNAL_NAME.upper()} — FULL-COMPANY WORKDAY STARTED ===")
    print(f"Target duration: {hours:g} hour(s)")
    print(f"Cycle interval: {cycle_minutes} minute(s)")
    print(f"Model-call guardrail: {max_calls}")
    print("Roster on shift: Atlas, Mercury, Forge, Freya, Nova, Satoshi, Midas, Oracle, Ledger, Sentinel")
    print("Core revenue crew: Oracle + Mercury + Forge + Sentinel every cycle")
    print("Department rotation: one of Atlas/Ledger/Nova/Freya/Midas/Satoshi each cycle")
    print(
        "Controlled email sending: "
        + (f"ENABLED (daily cap {daily_send_cap()})" if sending else "DISABLED")
    )
    print("Cash spending: DISABLED")
    print("Press Ctrl+C to stop safely.\n")

    try:
        while datetime.now() < deadline:
            # Worst-case model units per cycle:
            # core revenue loop up to 7 + one rotating department shift = 8.
            if calls_used + 8 > max_calls:
                remaining = max(0, int((deadline - datetime.now()).total_seconds() / 60))
                if not budget_idle_announced:
                    print(
                        f"API guardrail reached ({calls_used}/{max_calls}). "
                        f"The company will remain idle for the remaining ~{remaining} minute(s)."
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
                set_core_agent_action(
                    conn, "Oracle", f"Researching {category} prospects in {market}"
                )
                saved, duplicates, used = research_batch(
                    conn,
                    market=market,
                    category=category,
                    limit=prospects_per_cycle,
                    run_id=run_id,
                )
                calls_used += used
                set_core_agent_action(
                    conn,
                    "Oracle",
                    f"Researched {category} in {market}: {saved} new, {duplicates} duplicate(s)",
                    status="READY",
                )
                print(f"Oracle: {saved} saved, {duplicates} duplicate(s).")

                set_core_agent_action(conn, "Mercury", "Scoring researched prospects")
                scored, used = score_researched_prospects(
                    conn,
                    run_id=run_id,
                    limit=max(5, prospects_per_cycle),
                )
                calls_used += used
                set_core_agent_action(
                    conn,
                    "Mercury",
                    f"Scored {scored} prospect(s)",
                    status="READY",
                )
                print(f"Mercury: {scored} prospect(s) scored.")

                set_core_agent_action(conn, "Forge", "Producing evidence-based website audit")
                set_core_agent_action(conn, "Sentinel", "QA reviewing Forge audit")
                prospect_id, used = audit_best_prospect(conn, run_id=run_id)
                calls_used += used
                set_core_agent_action(
                    conn,
                    "Forge",
                    (
                        f"Audit processed for prospect #{prospect_id}"
                        if prospect_id is not None
                        else "No scored prospect needed an audit"
                    ),
                    status="READY",
                )
                set_core_agent_action(
                    conn,
                    "Sentinel",
                    "Audit QA completed",
                    status="READY",
                )
                if prospect_id is not None:
                    print(f"Forge/Sentinel: prospect #{prospect_id} audit processed.")

                set_core_agent_action(conn, "Mercury", "Drafting personalized outreach")
                set_core_agent_action(conn, "Sentinel", "QA reviewing outreach")
                prospect_id, used = draft_outreach_for_best(conn, run_id=run_id)
                calls_used += used
                set_core_agent_action(
                    conn,
                    "Mercury",
                    (
                        f"Outreach processed for prospect #{prospect_id}"
                        if prospect_id is not None
                        else "No audited prospect needed outreach"
                    ),
                    status="READY",
                )
                set_core_agent_action(
                    conn,
                    "Sentinel",
                    "Outreach QA completed",
                    status="READY",
                )
                if prospect_id is not None:
                    print(
                        f"Mercury/Sentinel: prospect #{prospect_id} "
                        "outreach draft processed."
                    )

                set_core_agent_action(conn, "Oracle", "Verifying public generic business contact")
                prospect_id, used = find_public_contact_for_best(conn, run_id=run_id)
                calls_used += used
                set_core_agent_action(
                    conn,
                    "Oracle",
                    (
                        f"Contact check processed for prospect #{prospect_id}"
                        if prospect_id is not None
                        else "No draft-ready prospect needed contact verification"
                    ),
                    status="READY",
                )
                if prospect_id is not None:
                    print(
                        f"Oracle: prospect #{prospect_id} public role contact checked."
                    )

                if sending:
                    set_core_agent_action(conn, "Mercury", "Executing guarded outbound sales")
                    set_core_agent_action(conn, "Sentinel", "Enforcing outbound send guardrails")
                    sent, skipped = send_ready_outreach(
                        conn,
                        run_id=run_id,
                        limit=1,
                    )
                    set_core_agent_action(
                        conn,
                        "Mercury",
                        f"Controlled outbound: {sent} sent, {skipped} skipped",
                        status="READY",
                    )
                    set_core_agent_action(
                        conn,
                        "Sentinel",
                        "Outbound guardrail check completed",
                        status="READY",
                    )
                    if sent or skipped:
                        print(
                            f"Resend: {sent} controlled outreach sent; "
                            f"{skipped} skipped by guardrails."
                        )

                department_agent, used = run_support_shift(
                    conn,
                    session_id=session_id,
                    run_id=run_id,
                    cycle=cycles,
                )
                calls_used += used
                print(f"{department_agent}: department shift completed.")

                update_work_session(
                    conn,
                    session_id,
                    cycles_completed=cycles,
                    estimated_calls_used=calls_used,
                    note=f"Last cycle: {category} in {market}; department={department_agent}",
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
            note="Full-company bounded workday completed.",
            ended=True,
        )
        end_shift(conn)
        print(f"\n=== {INTERNAL_NAME.upper()} — FULL-COMPANY WORKDAY COMPLETE ===")
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
        end_shift(conn)
        print(f"\n{INTERNAL_NAME} full-company workday stopped safely.")

    print("Review company with: python -m backend.status")
    print("Review pipeline with: python -m backend.prospects")


if __name__ == "__main__":
    main()
