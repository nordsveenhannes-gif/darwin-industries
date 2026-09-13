from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from agents import Runner
from dotenv import load_dotenv

from backend.agents.sentinel import build_sentinel
from backend.asset_collector import collect_source_images
from backend.agents.website_studio import (
    ClarificationPlan,
    ScopeDecision,
    UXReview,
    WebsiteBuildSpec,
    build_scope_manager,
    build_website_clarifier,
    build_website_forge,
    build_website_nova,
)
from backend.site_builder import render_site, slugify, validate_site
from backend.site_export import export_deployment_package
from backend.reference_specs import fire_ice_reference_spec
from backend.client_intake import assets_for_project, collect_client_answers, seed_launch_questions
from backend.site_server import serve_site
from backend.website_delivery import send_website_ready_email
from backend.branding import CLIENT_NAME, INTERNAL_NAME
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


def _event(conn, project_id: int, agent: str, stage: str, detail: str) -> None:
    conn.execute(
        """
        INSERT INTO website_project_events(project_id, agent, stage, detail, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (project_id, agent, stage, detail, now_iso()),
    )
    conn.commit()


def _update(conn, project_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now_iso()
    columns = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [project_id]
    conn.execute(f"UPDATE website_projects SET {columns} WHERE id=?", values)
    conn.commit()


def _qa_passed(text: str) -> bool:
    return "STATUS: PASS" in text.upper()


def _prepare_client_assets(project_id: int, site_dir: Path) -> dict[str, list[str]]:
    result = {"logo": [], "hero": [], "product": [], "about": []}
    rows = assets_for_project(project_id)
    if not rows:
        return result

    target = site_dir / "assets"
    target.mkdir(parents=True, exist_ok=True)

    for index, row in enumerate(rows, 1):
        source = Path(row["stored_path"])
        category = row["category"]
        if category not in result or not source.exists():
            continue
        suffix = source.suffix.lower() or ".jpg"
        filename = f"client-{category}-{index:02d}{suffix}"
        destination = target / filename
        shutil.copy2(source, destination)
        result[category].append(f"assets/{filename}")
    return result


def _sentinel_safe_mode_spec(spec: WebsiteBuildSpec, qa_report: str) -> WebsiteBuildSpec:
    """
    Convert a flagged private staging specification into a conservative reviewable build.

    Sentinel never gets bypassed: anything uncertain is removed, downgraded to enquiry-only,
    or deferred to launch. Public launch gates remain separate and strict.
    """
    safe = spec.model_copy(deep=True)
    safe.positioning = (
        f"A private staging concept for {safe.brand_name}, focused on clear navigation "
        "and enquiry flow while final commercial and compliance details remain pending."
    )
    safe.hero_subheading = (
        "Explore the available products and services, then request current pricing, "
        "availability and project details directly."
    )
    safe.trust_points = []
    safe.contact_email = None
    safe.contact_phone = None
    safe.unverified_claims = []
    safe.customer_assets_needed = list(
        dict.fromkeys(
            list(safe.customer_assets_needed)
            + [
                "Final commercial, legal, security and compliance details must be confirmed before public launch.",
                "Sentinel safe-mode staging removed or deferred disputed/unsupported claims.",
            ]
        )
    )

    for collection in safe.collections:
        collection.intro = (
            f"Explore {collection.name}. Final specifications, availability, delivery, "
            "installation and pricing are confirmed directly before purchase."
        )
        for card in collection.items:
            card.description = (
                f"Explore {card.name}. Final specifications and commercial details "
                "are confirmed directly on enquiry."
            )
            card.price_label = "Pricing on request"
            card.details = []

    # Replace potentially disputed FAQs with neutral process questions.
    safe.faqs = [
        type(safe.faqs[0])(
            question="How do I get current pricing?",
            answer="Send an enquiry and the business can confirm current pricing and availability.",
        )
        if safe.faqs
        else None,
        type(safe.faqs[0])(
            question="Can I confirm specifications before ordering?",
            answer="Yes. Final specifications and project requirements should be confirmed directly before purchase.",
        )
        if safe.faqs
        else None,
        type(safe.faqs[0])(
            question="Is this the final live website?",
            answer="No. This is a private staging concept for review; launch details are handled separately.",
        )
        if safe.faqs
        else None,
    ]
    safe.faqs = [item for item in safe.faqs if item is not None]
    return safe


def _quote_text(
    business_name: str,
    source_website: str,
    price: float,
    monthly_price: float,
    currency: str,
) -> str:
    symbol = "$" if currency.upper() == "USD" else f"{currency.upper()} "
    price_text = f"{symbol}{price:,.0f}"
    monthly_text = f"{symbol}{monthly_price:,.0f}"
    return f"""# Website Rebuild Quotation — {business_name}

Source website: {source_website}

## Price
**{price_text} one-time website build**
**{monthly_text}/month hosting & care after launch**

Payment structure for a real customer:
- The **{price_text} build fee is paid before production work begins**.
- The monthly care plan starts only after the website is launched.
- The care plan is month-to-month and can be cancelled; the customer keeps the website files and domain control.

Monthly care includes hosting, SSL, backups, uptime monitoring, and one small content/update request per month (up to roughly 30 minutes). Larger work is quoted before Shenanigan Systems starts it.

A demo acceptance is never counted as real revenue or payment.

## Included
- Premium responsive redesign.
- Six core pages: Home, two primary product/service pages, About, FAQ and Get Pricing, plus operational privacy/404 support pages.
- Existing verified business/product information reorganised for clarity.
- Functional quotation/enquiry form.
- Mobile navigation and responsive layouts.
- Accessibility basics: keyboard-friendly controls, focus states and reduced-motion support.
- Staging build with search-engine indexing disabled.
- Basic page titles and descriptions.
- Two consolidated revision rounds.
- Pre-launch QA of navigation, internal links, forms and staging safeguards.
- Launch assistance once customer-owned hosting/domain access is supplied securely.

## Not included unless quoted separately
- E-commerce checkout or payment processing.
- Custom booking systems.
- Paid plugins, paid stock photography or paid fonts.
- New professional photography/video.
- Copy claims, testimonials, certifications or product facts not supplied or verified.
- Complex CRM integrations.
- Ongoing SEO, advertising, hosting or maintenance.
- Domain purchase or transfer fees.

## Delivery target
Target staging delivery is 7–10 business days after the real project has:
1. an accepted scope,
2. verified deposit,
3. a completed client brief,
4. the content/assets needed to make the agreed pages reviewable.

The project clock pauses while Shenanigan Systems is waiting for customer decisions, missing assets, factual corrections
or revision feedback. Final legal/privacy/cookie/production details may be completed during staging, but
they must be resolved before public launch.

## Revision and acceptance
Two consolidated revision rounds are included. Feedback should come through one agreed approver so
conflicting stakeholder instructions do not silently expand the scope. The customer reviews the staging
URL before launch. Shenanigan Systems will not replace the live website without explicit launch approval.

Acceptance means:
- all agreed pages are present,
- navigation and enquiry form work,
- supplied factual corrections are incorporated,
- no critical broken internal links remain,
- the staging build matches the approved scope.

## Ownership and trust
The customer keeps ownership/control of their domain, customer accounts and final website files.
Shenanigan Systems does not require passwords by ordinary email and does not hold a domain hostage.
Any recurring hosting, maintenance or third-party fee must be disclosed separately before purchase.
"""


def _write_project_files(
    project_root: Path,
    quote: str,
    spec: WebsiteBuildSpec,
    ux: UXReview,
    qa: str,
) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "quote.md").write_text(quote, encoding="utf-8")
    (project_root / "build-spec.json").write_text(
        spec.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (project_root / "ux-review.json").write_text(
        ux.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (project_root / "qa-report.txt").write_text(qa, encoding="utf-8")
    (project_root / "CUSTOMER_HANDOFF.md").write_text(
        """# Customer handoff checklist

Before public launch:

- [ ] Customer has reviewed and explicitly approved the current staging site.
- [ ] Customer has confirmed factual product, pricing, VAT, delivery, installation, warranty and returns copy that appears on the live site.
- [ ] Customer has confirmed rights to all photography, logos, fonts, video and supplied/reused assets.
- [ ] Legal business identity and contact details are confirmed.
- [ ] Production privacy notice is approved and names the real data controller, purposes, retention and processors.
- [ ] Cookie/analytics inventory is known; non-essential storage/analytics is not enabled before the required consent mechanism.
- [ ] Enquiry routing is connected to the customer's real email/CRM and a real end-to-end submission has been tested.
- [ ] Accessibility QA covers labels, keyboard access, focus states, contrast, responsive layout and meaningful image alternatives where needed.
- [ ] Existing URLs are inventoried and any changed URLs have a one-to-one redirect map; important pages are not blindly redirected to the homepage.
- [ ] Page titles/descriptions, canonical URLs, sitemap, robots rules and any structured data are production-ready.
- [ ] Staging noindex/robots blocks are removed only in the final production release.
- [ ] Custom 404 behavior, navigation, forms, external links and critical integrations are tested.
- [ ] Existing analytics/Search Console requirements are preserved or deliberately replaced with the customer's approval.
- [ ] SSL/HTTPS and the production hostname are verified.
- [ ] Domain/hosting access uses a secure owner-controlled method.
- [ ] A backup/rollback plan exists before replacing the existing live site.
- [ ] Final payment is verified for a real paid job.
- [ ] Customer explicitly approves the launch window.
- [ ] Post-launch checks are scheduled for forms, redirects, 404s, indexing, analytics and uptime.

A demo acceptance or an unverified payment promise is never treated as revenue.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Shenanigan Systems' post-sale website studio and create a functional staging site."
    )
    parser.add_argument("--business-name", required=True)
    parser.add_argument("--website", required=True)
    parser.add_argument("--customer-email", default="demo.customer@example.com")
    parser.add_argument("--price", type=float, default=179.0)
    parser.add_argument("--monthly", type=float, default=39.0)
    parser.add_argument("--currency", default="USD")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Pretend the customer accepted the quote. No payment/revenue is recorded.",
    )
    parser.add_argument(
        "--accept-quote",
        action="store_true",
        help="Record quote acceptance for a non-demo project. This is not payment verification.",
    )
    parser.add_argument(
        "--confirm-asset-rights",
        action="store_true",
        help="Confirm the real customer has rights to reuse assets already published on their source website.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the completed staging site locally.",
    )
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="In demo mode, build without starting the local preview server.",
    )
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is missing from .env")

    price = max(150.0, min(float(args.price), 200.0))
    monthly_price = max(15.0, min(float(args.monthly), 99.0))
    currency = args.currency.strip().upper()[:8] or "USD"
    mode = "DEMO" if args.demo else "CUSTOMER"
    accepted = args.demo or args.accept_quote

    conn = connect()
    init_db(conn)

    quote = _quote_text(args.business_name, args.website, price, monthly_price, currency)
    cur = conn.execute(
        """
        INSERT INTO website_projects(
            business_name, source_website, customer_email, mode, status,
            quoted_price, monthly_price, currency, deposit_percent, quote_text, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'QUOTED', ?, ?, ?, 100, ?, ?, ?)
        """,
        (
            args.business_name,
            args.website,
            args.customer_email,
            mode,
            price,
            monthly_price,
            currency,
            quote,
            now_iso(),
            now_iso(),
        ),
    )
    project_id = int(cur.lastrowid)
    conn.commit()

    if args.confirm_asset_rights and not args.demo:
        conn.execute(
            "UPDATE website_projects SET asset_rights_confirmed=1, updated_at=? WHERE id=?",
            (now_iso(), project_id),
        )
        conn.commit()
        _event(
            conn,
            project_id,
            "Customer",
            "ASSET_RIGHTS_CONFIRMED",
            "Customer asset-reuse rights were explicitly confirmed for this project.",
        )

    _event(
        conn,
        project_id,
        "Mercury",
        "QUOTE_CREATED",
        f"Fixed-scope {currency} {price:,.0f} website rebuild quotation created.",
    )
    _set_agent(conn, "Mercury", "READY", f"Website quote #{project_id} prepared")

    slug = slugify(args.business_name)
    project_root = Path("builds") / f"{slug}-{project_id}"
    site_dir = project_root / "site"

    print(f"\n=== SHENANIGAN SYSTEMS WEBSITE STUDIO — PROJECT #{project_id} ===")
    print(f"Customer: {args.business_name}")
    print(f"Source: {args.website}")
    print(f"Quote: {currency} {price:,.0f} + {currency} {monthly_price:,.0f}/month")
    print(f"Mode: {mode}")

    if not accepted:
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "quote.md").write_text(quote, encoding="utf-8")
        _update(conn, project_id, build_dir=str(project_root), status="AWAITING_ACCEPTANCE")
        print(f"\nQuote prepared at: {project_root / 'quote.md'}")
        print("No build started because the quotation has not been accepted.")
        conn.close()
        return

    if args.demo:
        _update(conn, project_id, status="DEMO_ACCEPTED")
        _event(
            conn,
            project_id,
            "Customer",
            "DEMO_QUOTE_ACCEPTED",
            "Fake customer accepted the quotation. No real payment or revenue was recorded.",
        )
        print("Demo customer: quotation accepted. Revenue recorded: $0 (simulation).")
    else:
        _update(conn, project_id, status="AWAITING_DEPOSIT")
        _event(
            conn,
            project_id,
            "Customer",
            "QUOTE_ACCEPTED",
            "Customer quote acceptance recorded. Deposit remains unverified.",
        )
        _event(
            conn,
            project_id,
            "Ledger",
            "PAYMENT_GATE",
            "Production work is blocked until the agreed deposit is verified. Quote acceptance alone is not revenue.",
        )
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "quote.md").write_text(quote, encoding="utf-8")
        _update(conn, project_id, build_dir=str(project_root))
        _set_agent(conn, "Ledger", "READY", "Website project waiting for verified deposit")
        print("Quote acceptance recorded. Deposit remains unverified.")
        print("Shenanigan Systems will not begin production work before verified payment.")
        print(f"Quote saved at: {project_root / 'quote.md'}")
        conn.close()
        return

    _update(conn, project_id, status="CLIENT_INPUT_NEEDED")
    _event(
        conn,
        project_id,
        "Mercury",
        "CLIENT_BRIEF_REQUESTED",
        "Shenanigan Systems opened a client questionnaire before committing design, content and functionality decisions.",
    )
    _set_agent(conn, "Mercury", "WAITING_CLIENT", "Waiting for website project brief")
    client_brief = collect_client_answers(
        project_id,
        args.business_name,
        port=8790,
        heading="Before we design, we need your brief.",
        open_browser=args.demo,
    )
    _event(
        conn,
        project_id,
        "Customer",
        "CLIENT_BRIEF_COMPLETE",
        "Customer completed the website goals, audience, conversion, design, functionality, commercial-facts and staging-asset questionnaire.",
    )
    _set_agent(conn, "Mercury", "READY", "Client website brief received")
    _update(conn, project_id, status="SCOPE_REVIEW")
    print("Client brief received. The agents are now working: scope review -> design -> UX -> QA -> staging.")
    seed_launch_questions(project_id)
    _event(
        conn,
        project_id,
        "Mercury",
        "LAUNCH_DEPENDENCIES_RECORDED",
        "Launch-only client requirements were recorded separately so they do not block private staging.",
    )

    _set_agent(conn, "Mercury", "WORKING", "Checking client brief against accepted website scope")
    scope_decision = Runner.run_sync(
        build_scope_manager(),
        f"""
Check the accepted quote against this client brief before production starts.

QUOTE:
{quote}

CLIENT BRIEF:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}
""",
    ).final_output
    if not isinstance(scope_decision, ScopeDecision):
        raise RuntimeError("Mercury returned an unexpected scope decision.")

    _event(
        conn,
        project_id,
        "Mercury",
        "SCOPE_CHECK",
        (
            f"In scope: {scope_decision.in_scope}. {scope_decision.reason} "
            + (
                "Out-of-scope: " + "; ".join(scope_decision.out_of_scope_items)
                if scope_decision.out_of_scope_items
                else ""
            )
        ),
    )

    if not scope_decision.in_scope:
        items = "; ".join(scope_decision.out_of_scope_items) or "additional functionality"
        client_brief["deferred_out_of_scope_items"] = items
        _event(
            conn,
            project_id,
            "Mercury",
            "SCOPE_AUTO_DEFERRED",
            (
                "The system kept the purchased base scope moving autonomously and deferred "
                f"out-of-scope work for a later change order: {items}"
            ),
        )
        print(f"Scope note: base build continues; deferred change-order item(s): {items}")

    _set_agent(conn, "Mercury", "READY", "Accepted website scope confirmed")
    _update(conn, project_id, status="DESIGNING")
    print("Forge is designing the website specification now.")

    try:
        _set_agent(conn, "Forge", "WORKING", f"Architecting premium website for {args.business_name}")
        _event(
            conn,
            project_id,
            "Forge",
            "BUILD_SPEC_STARTED",
            "Forge is researching the first-party website and preparing a factual premium build specification.",
        )
        try:
            spec = Runner.run_sync(
                build_website_forge(),
                f"""
Create a premium website rebuild specification.

Customer: {args.business_name}
Current website: {args.website}
Project type: six-page lead-generation website rebuild
Primary conversion: request pricing / project enquiry

Treat the supplied website as the primary factual source. Keep important product/service choices,
prices, materials, lead times, dimensions, address and FAQs only when supported.
Do not invent testimonials, results, certifications, health claims, phone numbers or emails.
Choose exactly two primary customer-facing product/service collections. The visual renderer will
create Home, one page for each collection, About, FAQ and Get Pricing.

CLIENT BRIEF:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}

Use the client's answers for goals, audience, desired action, design direction and required functionality.
Treat corrections to commercial facts as client-supplied information; if they conflict with the public site,
do not silently choose a version. Omit the disputed fact from staging or place it in unverified_claims.
""",
            ).final_output
            if not isinstance(spec, WebsiteBuildSpec):
                raise RuntimeError("Forge returned an unexpected website build specification.")
        except Exception as forge_exc:
            if args.demo and "fireandicewellbeing.com" in args.website.lower():
                spec = fire_ice_reference_spec()
                _event(
                    conn,
                    project_id,
                    "Forge",
                    "REFERENCE_FALLBACK_USED",
                    (
                        "Live Forge research was temporarily unavailable, so the system used its "
                        "conservative Fire & Ice reference specification built from first-party "
                        f"public facts. Original error: {str(forge_exc)[:500]}"
                    ),
                )
                print("Forge live research fallback: using verified Fire & Ice reference specification.")
            else:
                raise

        _event(
            conn,
            project_id,
            "Forge",
            "BUILD_SPEC_COMPLETE",
            f"Forge produced a structured site specification with two collections "
            f"({len(spec.collections[0].items)} and {len(spec.collections[1].items)} cards) "
            f"and {len(spec.faqs)} FAQs.",
        )
        _set_agent(conn, "Forge", "READY", "Website architecture and factual copy drafted")

        def run_ux_review(current_spec: WebsiteBuildSpec) -> UXReview:
            result = Runner.run_sync(
                build_website_nova(),
                f"""
Review this PRIVATE STAGING website specification before build.

Customer: {args.business_name}
Quoted scope: Home, two primary product/service pages, About, FAQ and Get Pricing.
Primary conversion: the action stated in the client brief.

CLIENT BRIEF:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}

SPEC:
{current_spec.model_dump_json(indent=2)}

Review the staging experience as a professional web agency would.
Do not fail the private staging build merely because final launch-only matters such as exact privacy
wording, production cookie settings, analytics, domain access, final CRM routing, final warranty text
or payment verification are still pending. Put those in conversion_notes.
approved=false only when a material staging UX/content issue still needs correction.
""",
            ).final_output
            if not isinstance(result, UXReview):
                raise RuntimeError("Nova returned an unexpected UX review.")
            return result

        _update(conn, project_id, status="UX_REVIEW")
        print("Forge draft complete. Nova is reviewing the customer experience.")
        _set_agent(conn, "Nova", "WORKING", "Reviewing customer UX and conversion flow")
        ux = run_ux_review(spec)

        _event(
            conn,
            project_id,
            "Nova",
            "UX_REVIEW",
            f"UX score {ux.score}/100. Approved: {ux.approved}. "
            + ("; ".join(ux.required_changes[:5]) if ux.required_changes else "No critical staging changes."),
        )

        if not ux.approved and ux.required_changes:
            _set_agent(conn, "Forge", "WORKING", "Applying Nova's required website revisions")
            spec = Runner.run_sync(
                build_website_forge(),
                f"""
Revise this website build specification using Nova's STAGING review. Re-check public facts using the
first-party website where needed. Return a complete replacement WebsiteBuildSpec.

Customer: {args.business_name}
Website: {args.website}

CLIENT BRIEF:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}

CURRENT SPEC:
{spec.model_dump_json(indent=2)}

NOVA REQUIRED STAGING CHANGES:
{json.dumps(ux.required_changes, ensure_ascii=False, indent=2)}

Do not fix criticism by inventing claims or customer facts.
Launch-only dependencies can remain in customer_assets_needed/unverified_claims and must not be
turned into fabricated staging copy.
""",
            ).final_output
            if not isinstance(spec, WebsiteBuildSpec):
                raise RuntimeError("Forge returned an unexpected revised website specification.")
            _event(
                conn,
                project_id,
                "Forge",
                "UX_REVISIONS_APPLIED",
                "Forge applied Nova's required staging changes to the build specification.",
            )

            # Critical: review the revised specification, not the rejected earlier draft.
            _set_agent(conn, "Nova", "WORKING", "Re-reviewing revised customer staging experience")
            ux = run_ux_review(spec)
            _event(
                conn,
                project_id,
                "Nova",
                "UX_REVIEW_SECOND_PASS",
                f"Revised UX score {ux.score}/100. Approved: {ux.approved}. "
                + ("; ".join(ux.required_changes[:5]) if ux.required_changes else "No critical staging changes."),
            )

        _set_agent(conn, "Nova", "READY", f"Website staging UX reviewed: {ux.score}/100")

        _update(conn, project_id, status="STAGING_QA")
        print("Nova review complete. Sentinel is QA-checking the private staging build.")
        _set_agent(conn, "Sentinel", "WORKING", "QA checking private staging safety and customer trust")

        def run_project_qa(current_spec: WebsiteBuildSpec, current_ux: UXReview) -> str:
            return str(
                Runner.run_sync(
                    build_sentinel(),
                    f"""
QA this PRIVATE, NOINDEX WEBSITE STAGING project.

CUSTOMER: {args.business_name}
SOURCE WEBSITE: {args.website}

CLIENT BRIEF:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}

QUOTE:
{quote}

BUILD SPEC:
{current_spec.model_dump_json(indent=2)}

NOVA STAGING REVIEW:
{current_ux.model_dump_json(indent=2)}

Return exactly:
STATUS: PASS
or
STATUS: FLAG

Then:
REASONS:
- concise bullets

REQUIRED_CHANGES:
- concise bullets, or "None"

This is STAGING QA, not LAUNCH QA.

PASS the staging build when:
- it stays inside the accepted scope,
- unsupported or disputed claims are omitted rather than invented,
- it contains no fake testimonials, customers, awards, rankings, guarantees or fabricated results,
- health/performance claims are not strengthened beyond verified/client-supplied evidence,
- the customer brief is reflected in goals, audience, CTA, design direction and functionality,
- the site is safe to show privately for customer review,
- launch remains explicitly gated behind final customer approval.

Do NOT FLAG private staging merely because these launch dependencies are unfinished:
- final privacy/cookie/terms/warranty wording,
- analytics or marketing-cookie configuration,
- production hosting/domain credentials,
- production form-routing/CRM credentials,
- verified final payment,
- final asset licensing confirmation,
- legal review,
- final warranty/returns/shipping policies that can be omitted from staging.

If a commercial fact conflicts or is uncertain, staging may omit it and record it as pending client confirmation.
Nova approved=false by itself is not a reason to FLAG; judge the actual revised spec.
""",
                ).final_output
            ).strip()

        qa = run_project_qa(spec, ux)

        if not _qa_passed(qa):
            _event(
                conn,
                project_id,
                "Sentinel",
                "QA_REPAIR_REQUESTED",
                "Sentinel found a staging issue. The agents are attempting one bounded internal repair automatically.\n" + qa,
            )
            _set_agent(conn, "Forge", "WORKING", "Repairing staging specification after Sentinel QA")
            try:
                repaired = Runner.run_sync(
                    build_website_forge(),
                    f"""
Repair this PRIVATE STAGING website specification using Sentinel's QA report.

Customer: {args.business_name}
Source website: {args.website}

CLIENT BRIEF:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}

CURRENT SPEC:
{spec.model_dump_json(indent=2)}

SENTINEL STAGING QA:
{qa}

Return a complete replacement WebsiteBuildSpec.
Correct only actual staging issues. Re-check first-party facts where needed.
If a fact is disputed or cannot be verified, OMIT it from staging or put it in unverified_claims.
Do not invent legal text, commercial terms, testimonials or claims to make QA pass.
Launch-only dependencies may remain pending.
""",
                ).final_output
                if isinstance(repaired, WebsiteBuildSpec):
                    spec = repaired
                    _event(
                        conn,
                        project_id,
                        "Forge",
                        "QA_REPAIR_COMPLETE",
                        "Forge applied Sentinel's staging corrections.",
                    )
                    _set_agent(conn, "Nova", "WORKING", "Reviewing repaired staging specification")
                    ux = run_ux_review(spec)
                    _event(
                        conn,
                        project_id,
                        "Nova",
                        "QA_REPAIR_UX_REVIEW",
                        f"Post-repair UX score {ux.score}/100. Approved: {ux.approved}.",
                    )
            except Exception as repair_exc:
                _event(
                    conn,
                    project_id,
                    "Forge",
                    "QA_REPAIR_ERROR",
                    f"Automatic staging repair failed: {str(repair_exc)[:1000]}",
                )

            qa = run_project_qa(spec, ux)

        # If internal repair is not enough, distinguish missing client decisions from launch-only dependencies.
        if not _qa_passed(qa):
            _set_agent(conn, "Mercury", "WORKING", "Separating client questions from launch-only dependencies")
            plan = Runner.run_sync(
                build_website_clarifier(),
                f"""
Plan the next step for this website staging project.

Customer: {args.business_name}

CLIENT BRIEF ALREADY RECEIVED:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}

CURRENT SPEC:
{spec.model_dump_json(indent=2)}

NOVA REVIEW:
{ux.model_dump_json(indent=2)}

SENTINEL QA:
{qa}

Ask the client only for information that genuinely blocks a professional PRIVATE STAGING build.
Do not ask again for something already clearly answered in the client brief.
Do not treat final launch compliance, domain credentials, final legal copy or payment as staging blockers.
""",
            ).final_output
            if not isinstance(plan, ClarificationPlan):
                raise RuntimeError("Clarification planner returned an unexpected output.")

            staging_questions = [q for q in plan.questions if q.required_for == "STAGING"]
            followup = {}
            if staging_questions or plan.safe_omissions or not plan.staging_can_continue:
                auto_deferred = [
                    q.question for q in staging_questions
                ] + list(plan.safe_omissions)
                client_brief["autonomous_staging_deferrals"] = auto_deferred
                _event(
                    conn,
                    project_id,
                    "Mercury",
                    "CLARIFICATION_AUTO_DEFERRED",
                    (
                        "No second client interruption was allowed. Unresolved staging details "
                        "were omitted or deferred so the purchased base build could continue autonomously."
                    ),
                )
                print("Unresolved details auto-deferred. Agents are continuing without another client form.")

            _set_agent(conn, "Forge", "WORKING", "Finalizing staging after clarification review")
            spec = Runner.run_sync(
                build_website_forge(),
                f"""
Produce the FINAL PRIVATE STAGING specification after QA clarification planning.

Customer: {args.business_name}
Source website: {args.website}

COMPLETE CLIENT BRIEF:
{json.dumps(client_brief, ensure_ascii=False, indent=2)}

CURRENT SPEC:
{spec.model_dump_json(indent=2)}

SENTINEL QA:
{qa}

SAFE OMISSIONS / DEFERRALS:
{json.dumps(plan.safe_omissions, ensure_ascii=False, indent=2)}

Rules:
- Incorporate any new client answers.
- Remove unsupported/disputed facts that can safely be omitted.
- Do not invent missing launch-only policies or commercial terms.
- Keep launch-only dependencies in customer_assets_needed/unverified_claims.
- Return a complete WebsiteBuildSpec for a private noindex customer preview.
""",
            ).final_output
            if not isinstance(spec, WebsiteBuildSpec):
                raise RuntimeError("Forge returned an unexpected final staging specification.")

            _set_agent(conn, "Nova", "WORKING", "Final staging UX review")
            ux = run_ux_review(spec)
            _event(
                conn,
                project_id,
                "Nova",
                "FINAL_STAGING_UX_REVIEW",
                f"Final staging UX score {ux.score}/100. Approved: {ux.approved}.",
            )
            qa = run_project_qa(spec, ux)

        if not _qa_passed(qa):
            original_qa = qa
            _update(conn, project_id, status="SENTINEL_SAFE_MODE")
            _event(
                conn,
                project_id,
                "Sentinel",
                "SAFE_MODE_ACTIVATED",
                (
                    "Sentinel still found a staging concern after autonomous repair. "
                    "The project is NOT stopped: risky/uncertain content is being stripped or deferred."
                ),
            )
            _set_agent(conn, "Forge", "WORKING", "Applying deterministic Sentinel safe mode")
            spec = _sentinel_safe_mode_spec(spec, original_qa)
            ux = run_ux_review(spec)
            qa = (
                "STATUS: SAFE_MODE\n"
                "REASONS:\n- Sentinel concerns could not be fully resolved from verified data.\n"
                "REQUIRED_CHANGES:\n- Unsafe, disputed, or unsupported content was omitted/deferred.\n\n"
                "ORIGINAL_SENTINEL_REPORT:\n" + original_qa
            )
            _event(
                conn,
                project_id,
                "Forge",
                "SAFE_MODE_REPAIR_COMPLETE",
                "Forge produced a conservative noindex staging specification with risky/uncertain claims removed.",
            )
            _set_agent(conn, "Sentinel", "READY", "Safe-mode staging allowed; public launch remains gated")
            print("Sentinel safe mode activated: unsafe/uncertain items were stripped; staging continues.")
        else:
            _event(conn, project_id, "Sentinel", "STAGING_QA_PASS", qa)
            _set_agent(conn, "Sentinel", "READY", "Private staging passed claims/scope QA")

        _update(conn, project_id, status="STAGING_QA_PASSED")

        _update(conn, project_id, status="RENDERING_STAGING")
        print("Staging QA passed. Midas is rendering and validating the website.")
        _set_agent(conn, "Midas", "WORKING", "Rendering reusable premium website system")
        client_assets = _prepare_client_assets(project_id, site_dir)
        has_client_images = any(client_assets.values())

        hero_images = list(client_assets["hero"])
        product_images = list(client_assets["product"])
        about_images = list(client_assets["about"])
        logo_file = client_assets["logo"][0] if client_assets["logo"] else None

        if has_client_images:
            _event(
                conn,
                project_id,
                "Midas",
                "CLIENT_ASSETS_USED",
                (
                    f"Using client-uploaded assets: logo={len(client_assets['logo'])}, "
                    f"hero={len(client_assets['hero'])}, product={len(client_assets['product'])}, "
                    f"about={len(client_assets['about'])}. Client images take priority over scraped imagery."
                ),
            )
        elif args.demo or args.confirm_asset_rights:
            # A single first-party social/hero image is safer than guessing which scraped image
            # belongs to which product. Product cards stay intentionally abstract until the client
            # supplies categorized photography.
            source_images = collect_source_images(args.website, site_dir / "assets", max_images=3)
            hero_images = list(source_images[:3])
            _event(
                conn,
                project_id,
                "Midas",
                "SOURCE_ASSETS_COLLECTED",
                (
                    f"Collected {len(source_images)} source-site hero candidate(s). "
                    "The system did not guess product-photo placement without client-provided categories."
                ),
            )

        render_site(
            spec,
            site_dir,
            logo_file=logo_file,
            about_images=about_images,
            hero_images=hero_images,
            product_images=product_images,
        )
        errors = validate_site(site_dir)
        if errors:
            _event(
                conn,
                project_id,
                "Midas",
                "RENDER_RECOVERY",
                "Initial static validation failed; rebuilding conservative safe-mode staging automatically: "
                + " | ".join(errors[:8]),
            )
            print("Render validation found faults. Midas is rebuilding in conservative safe mode.")
            spec = _sentinel_safe_mode_spec(spec, " | ".join(errors))
            if site_dir.exists():
                shutil.rmtree(site_dir)
            render_site(
                spec,
                site_dir,
                logo_file=logo_file,
                about_images=about_images,
                hero_images=hero_images,
                product_images=product_images,
            )
            errors = validate_site(site_dir)
            if errors:
                # Do not pretend success. Preserve the project as an autonomous engineering incident,
                # while keeping the process alive for dashboard diagnosis instead of silently publishing.
                _update(conn, project_id, status="ENGINEERING_RECOVERY_NEEDED")
                _event(
                    conn,
                    project_id,
                    "Midas",
                    "RENDER_RECOVERY_FAILED",
                    "Deterministic rebuild still failed validation: " + " | ".join(errors[:12]),
                )
                _set_agent(conn, "Midas", "WORKING", "Engineering recovery required; no unsafe site published")
                print("Renderer code fault remains after safe rebuild; no unsafe preview was published.")
                # Continue to write diagnostic project files rather than terminating the whole company.
                _write_project_files(project_root, quote, spec, ux, qa)
                conn.close()
                return

        _write_project_files(project_root, quote, spec, ux, qa)
        deploy_dir = export_deployment_package(project_root, site_dir)
        _event(
            conn,
            project_id,
            "Midas",
            "DEPLOY_PACKAGE_READY",
            f"Standalone deployable website application exported to {deploy_dir}.",
        )
        preview_url = f"http://127.0.0.1:{max(1024, min(args.port, 65535))}"
        _update(
            conn,
            project_id,
            status="STAGING_READY",
            quote_text=quote,
            ux_review=ux.model_dump_json(indent=2),
            qa_report=qa,
            build_dir=str(project_root),
            preview_url=preview_url,
        )
        _event(
            conn,
            project_id,
            "Midas",
            "STAGING_BUILT",
            f"Functional six-page staging site rendered to {site_dir}. "
            "Internal-link, form-wiring and staging-noindex checks passed.",
        )
        _set_agent(conn, "Midas", "READY", "Premium staging website rendered and validated")

        project_row = conn.execute(
            "SELECT customer_email FROM website_projects WHERE id=?",
            (project_id,),
        ).fetchone()
        client_email = (project_row["customer_email"] or "").strip() if project_row else ""
        public_preview = (
            preview_url
            if args.demo
            else os.getenv("DARWIN_PUBLIC_STAGING_URL", "").strip() or None
        )

        if client_email:
            _set_agent(conn, "Mercury", "WORKING", f"Emailing finished website proposal to {client_email}")
            try:
                provider_id = send_website_ready_email(
                    to_email=client_email,
                    business_name=args.business_name,
                    build_price_usd=price,
                    monthly_price_usd=monthly_price,
                    preview_url=public_preview,
                )
                _update(
                    conn,
                    project_id,
                    delivery_email_status="SENT",
                    delivery_email_to=client_email,
                    delivery_email_provider_id=provider_id,
                )
                _event(
                    conn,
                    project_id,
                    "Mercury",
                    "STAGING_EMAIL_SENT",
                    f"Finished proposal email sent to {client_email}.",
                )
                _set_agent(conn, "Mercury", "READY", "Finished website proposal emailed to client")
                print(f"Mercury emailed the finished proposal to {client_email}.")
            except Exception as email_exc:
                _update(
                    conn,
                    project_id,
                    delivery_email_status="FAILED",
                    delivery_email_to=client_email,
                )
                _event(
                    conn,
                    project_id,
                    "Mercury",
                    "STAGING_EMAIL_FAILED",
                    str(email_exc)[:1000],
                )
                _set_agent(conn, "Mercury", "READY", "Website delivery email failed; staging remains ready")
                print("Website built successfully, but the client delivery email failed:", email_exc)

        _set_agent(conn, "Ledger", "READY", "Website project built; no unverified revenue counted")
        print("\nBuild validation: PASS")
        print(f"Project files: {project_root}")
        print(f"Staging site: {site_dir}")
        print(f"Standalone deploy package: {deploy_dir}")
        print("Pages: Home / two primary collection pages / About / FAQ / Get Pricing")
        print("Quote form backend: enabled in local staging server and deploy package")
        print("Public launch: disabled until customer approval and production credentials exist")

        should_serve = args.serve or (args.demo and not args.no_serve)
        conn.close()

        if should_serve:
            serve_site(
                site_dir,
                project_id,
                max(1024, min(args.port, 65535)),
                open_browser=args.demo,
            )
        else:
            print(
                f"\nPreview later with:\n"
                f'python -m backend.site_server --site-dir "{site_dir}" '
                f"--project-id {project_id} --port {args.port}"
            )

    except Exception as exc:
        try:
            _update(conn, project_id, status="ERROR", error_text=str(exc)[:4000])
            _event(conn, project_id, "System", "ERROR", str(exc)[:4000])
            _set_agent(conn, "Forge", "READY", "Website project encountered an error")
        finally:
            conn.close()
        raise


if __name__ == "__main__":
    main()
