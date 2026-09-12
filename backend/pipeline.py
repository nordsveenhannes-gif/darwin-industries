import json

from agents import Runner

from backend.agents.contact_finder import PublicBusinessContact, build_contact_finder
from backend.agents.forge_web import WebsiteAudit, build_field_forge
from backend.agents.mercury import (
    OutreachDraft,
    ProspectScoreBatch,
    build_mercury_outreach,
    build_mercury_scorer,
)
from backend.agents.sentinel import build_sentinel
from backend.emailer import is_safe_business_email, minimum_sales_score
from backend.storage import now_iso, save_event


def _run(agent, prompt):
    return Runner.run_sync(agent, prompt).final_output


def score_researched_prospects(conn, run_id: int | None, limit: int = 5) -> tuple[int, int]:
    rows = conn.execute(
        """
        SELECT * FROM prospects
        WHERE sales_score IS NULL
          AND status='RESEARCHED'
        ORDER BY confidence DESC, id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    if not rows:
        return 0, 0

    items = []
    for row in rows:
        items.append(
            {
                "prospect_id": row["id"],
                "business_name": row["business_name"],
                "website_url": row["website_url"],
                "market": row["market"],
                "category": row["category"],
                "observed_issue": row["observed_issue"],
                "why_fit": row["why_fit"],
                "research_confidence": row["confidence"],
            }
        )

    prompt = (
        "Score these researched prospects. Return one score for every prospect_id.\n\n"
        + json.dumps(items, indent=2)
    )
    output = _run(build_mercury_scorer(), prompt)
    if not isinstance(output, ProspectScoreBatch):
        raise RuntimeError("Mercury returned an unexpected scoring output.")

    allowed = {row["id"] for row in rows}
    updated = 0
    for item in output.prospects:
        if item.prospect_id not in allowed:
            continue
        conn.execute(
            """
            UPDATE prospects
            SET sales_score=?,
                sales_reason=?,
                recommended_angle=?,
                status='SCORED',
                updated_at=?
            WHERE id=?
            """,
            (
                item.score,
                item.rationale,
                item.recommended_angle,
                now_iso(),
                item.prospect_id,
            ),
        )
        updated += 1
    conn.commit()

    if run_id is not None:
        save_event(
            conn,
            run_id,
            "PROSPECTS_SCORED",
            f"Mercury scored {updated} researched prospect(s).",
        )

    return updated, 1


def audit_best_prospect(conn, run_id: int | None) -> tuple[int | None, int]:
    row = conn.execute(
        """
        SELECT * FROM prospects
        WHERE audit_text IS NULL
          AND status='SCORED'
          AND sales_score IS NOT NULL
        ORDER BY sales_score DESC, confidence DESC, id ASC
        LIMIT 1
        """
    ).fetchone()

    if not row:
        return None, 0

    prompt = f"""
Audit this real public website as an internal Darwin Industries work product.

Business: {row['business_name']}
Website: {row['website_url']}
Market: {row['market']}
Category: {row['category']}
Oracle observation: {row['observed_issue']}
Oracle sources: {row['source_urls_json']}

Produce an evidence-based audit with exactly three prioritized improvements.
"""

    audit = _run(build_field_forge(), prompt)
    if not isinstance(audit, WebsiteAudit):
        raise RuntimeError("Forge returned an unexpected audit output.")

    if not audit.sufficient_evidence:
        conn.execute(
            """
            UPDATE prospects
            SET status='RESEARCH_REJECTED',
                audit_text=?,
                updated_at=?
            WHERE id=?
            """,
            (audit.audit_markdown, now_iso(), row["id"]),
        )
        conn.commit()
        return row["id"], 1

    qa_prompt = f"""
Audit this Darwin Industries internal website-audit draft.

PROSPECT:
{row['business_name']} — {row['website_url']}

ORIGINAL RESEARCH:
{row['observed_issue']}
Sources: {row['source_urls_json']}

FORGE AUDIT:
{audit.audit_markdown}

FORGE EVIDENCE URLS:
{json.dumps(audit.evidence_urls)}

Return exactly:
STATUS: PASS
or
STATUS: FLAG

Then:
REASONS:
- concise bullets

REQUIRED_CHANGES:
- concise bullets, or "None"

Pass only if the audit is modest, truthful, evidence-based, has exactly three prioritized improvements,
contains no invented customer/revenue/performance claims, and remains internal with no external action.
"""
    qa = _run(build_sentinel(), qa_prompt)
    passed = "STATUS: PASS" in qa.upper()

    conn.execute(
        """
        UPDATE prospects
        SET audit_text=?,
            audit_qa=?,
            status=?,
            updated_at=?
        WHERE id=?
        """,
        (
            audit.audit_markdown,
            qa,
            "AUDITED" if passed else "AUDIT_FLAGGED",
            now_iso(),
            row["id"],
        ),
    )
    conn.commit()

    if run_id is not None:
        save_event(
            conn,
            run_id,
            "PROSPECT_AUDITED",
            f"Forge audited prospect #{row['id']}; QA={'PASS' if passed else 'FLAG'}.",
        )

    return row["id"], 2


def draft_outreach_for_best(conn, run_id: int | None) -> tuple[int | None, int]:
    row = conn.execute(
        """
        SELECT * FROM prospects
        WHERE status='AUDITED'
          AND outreach_body IS NULL
          AND audit_text IS NOT NULL
        ORDER BY sales_score DESC, confidence DESC, id ASC
        LIMIT 1
        """
    ).fetchone()

    if not row:
        return None, 0

    prompt = f"""
Draft one email for this prospect.

Business: {row['business_name']}
Website: {row['website_url']}
Market: {row['market']}
Category: {row['category']}
Observed public issue: {row['observed_issue']}
Sales angle: {row['recommended_angle']}

Internal audit:
{row['audit_text']}

Do not send it. Produce only a draft.
"""
    draft = _run(build_mercury_outreach(), prompt)
    if not isinstance(draft, OutreachDraft):
        raise RuntimeError("Mercury returned an unexpected outreach output.")

    qa_prompt = f"""
Review this UNSENT outreach draft.

Business: {row['business_name']}
Public observation: {row['observed_issue']}

Subject:
{draft.subject}

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

Pass only if it is truthful, short, respectful, personalized from supplied facts,
contains no fake urgency or guarantees, includes an easy opt-out, and clearly remains unsent.
"""
    qa = _run(build_sentinel(), qa_prompt)
    passed = "STATUS: PASS" in qa.upper()

    conn.execute(
        """
        UPDATE prospects
        SET outreach_subject=?,
            outreach_body=?,
            outreach_qa=?,
            status=?,
            updated_at=?
        WHERE id=?
        """,
        (
            draft.subject,
            draft.body,
            qa,
            "DRAFT_READY" if passed else "OUTREACH_FLAGGED",
            now_iso(),
            row["id"],
        ),
    )
    conn.commit()

    if run_id is not None:
        save_event(
            conn,
            run_id,
            "OUTREACH_DRAFTED",
            f"Mercury drafted outreach for prospect #{row['id']}; QA={'PASS' if passed else 'FLAG'}. No email sent.",
        )

    return row["id"], 2


def find_public_contact_for_best(conn, run_id: int | None) -> tuple[int | None, int]:
    row = conn.execute(
        """
        SELECT * FROM prospects
        WHERE status='DRAFT_READY'
          AND contact_email IS NULL
          AND COALESCE(sales_score, 0) >= ?
        ORDER BY sales_score DESC, confidence DESC, id ASC
        LIMIT 1
        """,
        (minimum_sales_score(),),
    ).fetchone()

    if not row:
        return None, 0

    prompt = f"""
Find a safe public business contact email for this exact prospect.

Prospect ID: {row['id']}
Business: {row['business_name']}
Official website: {row['website_url']}
Market: {row['market']}
Category: {row['category']}
Research sources: {row['source_urls_json']}

Return only an explicitly published generic role/business email from the official business website.
Do not guess. Do not return a named person's email. If none is safely available, set eligible=false.
"""
    contact = _run(build_contact_finder(), prompt)
    if not isinstance(contact, PublicBusinessContact):
        raise RuntimeError("Contact verifier returned an unexpected output.")

    eligible = (
        contact.prospect_id == row["id"]
        and contact.eligible
        and is_safe_business_email(contact.email, row["website_url"])
        and bool(contact.source_url)
        and contact.confidence >= 70
    )

    conn.execute(
        """
        UPDATE prospects
        SET contact_email=?,
            contact_email_source=?,
            contact_email_kind=?,
            contact_confidence=?,
            status=?,
            updated_at=?
        WHERE id=?
        """,
        (
            contact.email.strip().lower() if eligible and contact.email else None,
            contact.source_url if eligible else contact.source_url,
            "PUBLIC_ROLE" if eligible else None,
            contact.confidence,
            "CONTACT_READY" if eligible else "CONTACT_UNAVAILABLE",
            now_iso(),
            row["id"],
        ),
    )
    conn.commit()

    if run_id is not None:
        save_event(
            conn,
            run_id,
            "CONTACT_VERIFIED" if eligible else "CONTACT_UNAVAILABLE",
            (
                f"Public role contact verified for prospect #{row['id']}."
                if eligible
                else f"No safe public role contact verified for prospect #{row['id']}."
            ),
        )

    return row["id"], 1
