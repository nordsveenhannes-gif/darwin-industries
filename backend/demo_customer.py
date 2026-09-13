import argparse
import os
import time

import resend
from agents import Runner
from dotenv import load_dotenv

from backend.agents.customer_demo import CustomerDiscovery, build_customer_discovery
from backend.agents.forge_web import WebsiteAudit, build_field_forge
from backend.agents.mercury import OutreachDraft, build_mercury_outreach
from backend.agents.sentinel import build_sentinel
from backend.storage import connect, init_db, now_iso


def _set_agent(conn, agent: str, status: str, action: str) -> None:
    conn.execute(
        """
        UPDATE agent_state
        SET status=?, last_action=?, updated_at=?
        WHERE agent=?
        """,
        (status, action, now_iso(), agent),
    )
    conn.commit()


def _journey_event(conn, journey_id: int, agent: str, stage: str, detail: str) -> None:
    conn.execute(
        """
        INSERT INTO journey_events(journey_id, agent, stage, detail, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (journey_id, agent, stage, detail, now_iso()),
    )
    conn.commit()


def _update_journey(conn, journey_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now_iso()
    columns = ", ".join(f"{name}=?" for name in fields)
    values = list(fields.values()) + [journey_id]
    conn.execute(
        f"UPDATE customer_journeys SET {columns} WHERE id=?",
        values,
    )
    conn.commit()


def _qa_passed(text: str) -> bool:
    return "STATUS: PASS" in text.upper()


def _pace(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _send_demo_email(to_email: str, subject: str, body: str) -> str:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("DARWIN_EMAIL_FROM", "").strip()
    reply_to = os.getenv("DARWIN_EMAIL_REPLY_TO", "").strip()

    if not api_key or not from_email or not reply_to:
        raise RuntimeError(
            "Demo send requires RESEND_API_KEY, DARWIN_EMAIL_FROM, and "
            "DARWIN_EMAIL_REPLY_TO in .env."
        )

    resend.api_key = api_key
    response = resend.Emails.send(
        {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": body,
            "reply_to": reply_to,
            "tags": [{"name": "source", "value": "darwin_customer_demo"}],
        }
    )
    if isinstance(response, dict):
        return str(response.get("id") or "")
    return str(getattr(response, "id", "") or "")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a consented, real-time Shenanigan Systems customer journey demo."
    )
    parser.add_argument("--business-name", required=True)
    parser.add_argument("--website", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the final QA-approved demo email to the supplied address.",
    )
    parser.add_argument(
        "--pace-seconds",
        type=float,
        default=4.0,
        help="Pause between stages so the dashboard is easy to follow.",
    )
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing from .env")

    conn = connect()
    init_db(conn)

    cur = conn.execute(
        """
        INSERT INTO customer_journeys(
            business_name, website_url, customer_email, status, created_at, updated_at
        )
        VALUES (?, ?, ?, 'STARTED', ?, ?)
        """,
        (args.business_name, args.website, args.email, now_iso(), now_iso()),
    )
    journey_id = int(cur.lastrowid)
    conn.commit()

    print(f"\nShenanigan Systems customer journey #{journey_id} started.")
    print("Open the live monitor in another window with: python -m backend.dashboard")
    print("Then visit: http://127.0.0.1:8765\n")

    try:
        _set_agent(conn, "Oracle", "WORKING", f"Inspecting {args.website} for customer demo")
        _journey_event(
            conn,
            journey_id,
            "Oracle",
            "DISCOVERY_STARTED",
            f"Oracle is inspecting {args.website} and looking for one evidence-based lead/conversion issue.",
        )
        discovery = Runner.run_sync(
            build_customer_discovery(),
            f"""
Run a consented customer demo for Shenanigan Systems.

Business: {args.business_name}
Website: {args.website}

Find one careful, public, evidence-based website observation that could matter for conversion
or lead generation. This is a demonstration for the business owner.
""",
        ).final_output
        if not isinstance(discovery, CustomerDiscovery):
            raise RuntimeError("Oracle returned an unexpected demo discovery output.")

        _update_journey(
            conn,
            journey_id,
            status="DISCOVERED",
            observation=discovery.observed_issue,
            discovery_evidence="\n".join(discovery.evidence_urls),
        )
        _journey_event(
            conn,
            journey_id,
            "Oracle",
            "DISCOVERY_COMPLETE",
            (
                f"Observation: {discovery.observed_issue}\n"
                f"Why it matters: {discovery.why_it_matters}\n"
                f"Confidence: {discovery.confidence}%"
            ),
        )
        _set_agent(conn, "Oracle", "READY", "Customer demo discovery completed")
        _pace(args.pace_seconds)

        _set_agent(conn, "Forge", "WORKING", f"Building audit for {args.business_name}")
        _journey_event(
            conn,
            journey_id,
            "Forge",
            "AUDIT_STARTED",
            "Forge is turning Oracle's observation into a focused 3-improvement website audit.",
        )
        audit = Runner.run_sync(
            build_field_forge(),
            f"""
Create an evidence-based customer-facing audit draft.

Business: {args.business_name}
Website: {args.website}
Oracle observation: {discovery.observed_issue}
Oracle evidence: {discovery.evidence_urls}

Produce exactly three prioritized improvements. Be useful and specific, but never invent facts,
rankings, traffic, leads, revenue impact, or rendered/mobile evidence you did not verify.
""",
        ).final_output
        if not isinstance(audit, WebsiteAudit):
            raise RuntimeError("Forge returned an unexpected demo audit output.")

        _update_journey(
            conn,
            journey_id,
            status="AUDIT_DRAFTED",
            audit_text=audit.audit_markdown,
        )
        _journey_event(conn, journey_id, "Forge", "AUDIT_DRAFTED", audit.audit_markdown)
        _set_agent(conn, "Forge", "READY", "Customer demo audit drafted")
        _pace(args.pace_seconds)

        _set_agent(conn, "Sentinel", "WORKING", "QA reviewing demo audit")
        _journey_event(
            conn,
            journey_id,
            "Sentinel",
            "AUDIT_QA_STARTED",
            "Sentinel is checking the audit for unsupported claims, scope creep, and exactly three priorities.",
        )
        audit_qa = str(
            Runner.run_sync(
                build_sentinel(),
                f"""
Review this customer-facing audit draft.

Business: {args.business_name}
Website: {args.website}
Oracle observation: {discovery.observed_issue}

AUDIT:
{audit.audit_markdown}

Return exactly:
STATUS: PASS
or
STATUS: FLAG

Then:
REASONS:
- concise bullets

REQUIRED_CHANGES:
- concise bullets, or "None"

Pass only if the audit is truthful, evidence-based, modest, useful, and has exactly three
prioritized improvements with no invented performance/revenue claims.
""",
            ).final_output
        ).strip()
        audit_pass = _qa_passed(audit_qa)
        _update_journey(
            conn,
            journey_id,
            status="AUDIT_QA_PASS" if audit_pass else "AUDIT_QA_FLAG",
            audit_qa=audit_qa,
        )
        _journey_event(
            conn,
            journey_id,
            "Sentinel",
            "AUDIT_QA_PASS" if audit_pass else "AUDIT_QA_FLAG",
            audit_qa,
        )
        _set_agent(conn, "Sentinel", "READY", "Customer demo audit QA completed")
        if not audit_pass:
            print("Sentinel flagged the audit. Demo stopped safely.")
            return
        _pace(args.pace_seconds)

        _set_agent(conn, "Mercury", "WORKING", f"Writing customer approach for {args.business_name}")
        _journey_event(
            conn,
            journey_id,
            "Mercury",
            "OUTREACH_STARTED",
            "Mercury is converting the approved research into a short customer email.",
        )
        draft = Runner.run_sync(
            build_mercury_outreach(),
            f"""
Draft a short first-contact email for this consented customer demo.

Business: {args.business_name}
Website: {args.website}
Public observation: {discovery.observed_issue}
Approved internal audit:
{audit.audit_markdown}

Offer Shenanigan Systems' 48-hour website lead audit for $129.
Do not invent familiarity, urgency, customers, guarantees, or a payment link.
Include an easy opt-out.
""",
        ).final_output
        if not isinstance(draft, OutreachDraft):
            raise RuntimeError("Mercury returned an unexpected demo outreach output.")

        _update_journey(
            conn,
            journey_id,
            status="OUTREACH_DRAFTED",
            outreach_subject=draft.subject,
            outreach_body=draft.body,
        )
        _journey_event(
            conn,
            journey_id,
            "Mercury",
            "OUTREACH_DRAFTED",
            f"Subject: {draft.subject}\n\n{draft.body}",
        )
        _set_agent(conn, "Mercury", "READY", "Customer demo outreach drafted")
        _pace(args.pace_seconds)

        _set_agent(conn, "Sentinel", "WORKING", "QA reviewing customer email")
        outreach_qa = str(
            Runner.run_sync(
                build_sentinel(),
                f"""
Review this customer outreach email.

Business: {args.business_name}
Observation: {discovery.observed_issue}
Subject: {draft.subject}
Body:
{draft.body}

Return exactly:
STATUS: PASS
or
STATUS: FLAG

Then:
REASONS:
- concise bullets

REQUIRED_CHANGES:
- concise bullets, or "None"

Pass only if it is truthful, relevant, respectful, under 140 words, has no guarantees/fake
urgency, and includes an easy opt-out.
""",
            ).final_output
        ).strip()
        outreach_pass = _qa_passed(outreach_qa)
        _update_journey(
            conn,
            journey_id,
            status="OUTREACH_QA_PASS" if outreach_pass else "OUTREACH_QA_FLAG",
            outreach_qa=outreach_qa,
        )
        _journey_event(
            conn,
            journey_id,
            "Sentinel",
            "OUTREACH_QA_PASS" if outreach_pass else "OUTREACH_QA_FLAG",
            outreach_qa,
        )
        _set_agent(conn, "Sentinel", "READY", "Customer demo outreach QA completed")
        if not outreach_pass:
            print("Sentinel flagged the outreach. Demo stopped safely.")
            return
        _pace(args.pace_seconds)

        if args.send:
            _set_agent(conn, "Mercury", "WORKING", f"Sending consented demo to {args.email}")
            _journey_event(
                conn,
                journey_id,
                "Mercury",
                "EMAIL_SEND_STARTED",
                f"Sending the QA-approved demonstration email to {args.email}.",
            )
            provider_id = _send_demo_email(args.email, draft.subject, draft.body)
            _update_journey(
                conn,
                journey_id,
                status="EMAIL_SENT",
                email_status="SENT",
                provider_message_id=provider_id,
            )
            _journey_event(
                conn,
                journey_id,
                "Mercury",
                "EMAIL_SENT",
                f"Email sent successfully to {args.email}. Provider id: {provider_id or 'recorded by provider'}.",
            )
            _set_agent(conn, "Mercury", "READY", "Customer demo email sent")
        else:
            _update_journey(
                conn,
                journey_id,
                status="READY_TO_SEND",
                email_status="NOT_SENT",
            )
            _journey_event(
                conn,
                journey_id,
                "Mercury",
                "READY_TO_SEND",
                "The customer email is QA-approved. It was not sent because --send was not supplied.",
            )

        _journey_event(
            conn,
            journey_id,
            "Ledger",
            "PAYMENT_GATE",
            (
                "Next real customer step would be payment. Stripe checkout/webhook is not yet wired "
                "into the system, so the demo stops here rather than pretending revenue happened."
            ),
        )
        _set_agent(conn, "Ledger", "READY", "Payment integration is the next customer-journey gap")
        print("\nCustomer demo complete.")
        print("The demo stopped at the real payment boundary; no revenue was fabricated.")

    except Exception as exc:
        _update_journey(conn, journey_id, status="ERROR", error_text=str(exc)[:2000])
        _journey_event(conn, journey_id, "System", "ERROR", str(exc))
        raise


if __name__ == "__main__":
    main()
