from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents import Runner
from dotenv import load_dotenv

from backend.agents.sentinel import build_sentinel
from backend.agents.website_studio import (
    UXReview,
    WebsiteBuildSpec,
    build_website_forge,
    build_website_nova,
)
from backend.site_builder import render_site, validate_site
from backend.site_export import export_deployment_package
from backend.site_server import serve_site
from backend.storage import connect, init_db, now_iso


def _set_agent(conn, agent: str, status: str, action: str) -> None:
    conn.execute(
        "UPDATE agent_state SET status=?,last_action=?,updated_at=? WHERE agent=?",
        (status, action, now_iso(), agent),
    )
    conn.commit()


def _event(conn, project_id: int, agent: str, stage: str, detail: str) -> None:
    conn.execute(
        """INSERT INTO website_project_events(project_id,agent,stage,detail,created_at)
        VALUES(?,?,?,?,?)""",
        (project_id, agent, stage, detail, now_iso()),
    )
    conn.commit()


def _qa_passed(text: str) -> bool:
    return "STATUS: PASS" in text.upper()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply one customer revision round to a Darwin staging website."
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--feedback", required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()

    load_dotenv()
    conn = connect()
    init_db(conn)

    project = conn.execute(
        "SELECT * FROM website_projects WHERE id=?", (args.project_id,)
    ).fetchone()
    if not project:
        raise SystemExit(f"Website project #{args.project_id} does not exist.")
    if project["status"] not in {"STAGING_READY", "STAGING_APPROVED"}:
        raise SystemExit(
            f"Project is {project['status']}; revisions are available after a staging build."
        )

    used = int(project["revision_rounds_used"] or 0)
    if used >= 2:
        raise SystemExit(
            "The quoted two revision rounds are already used. Create a change order instead "
            "of silently expanding scope."
        )

    project_root = Path(project["build_dir"])
    site_dir = project_root / "site"
    spec_path = project_root / "build-spec.json"
    if not spec_path.exists():
        raise SystemExit(f"Build specification is missing: {spec_path}")

    spec = WebsiteBuildSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
    feedback = args.feedback.strip()
    if not feedback:
        raise SystemExit("Customer feedback cannot be empty.")

    _event(
        conn,
        args.project_id,
        "Customer",
        "REVISION_REQUESTED",
        f"Revision round {used + 1}: {feedback[:1500]}",
    )

    try:
        _set_agent(
            conn,
            "Forge",
            "WORKING",
            f"Applying customer revision round {used + 1} to website project #{args.project_id}",
        )
        revised = Runner.run_sync(
            build_website_forge(),
            f"""
Revise this existing customer website build specification.

Customer: {project['business_name']}
Source website: {project['source_website']}
This is revision round {used + 1} of the two included rounds.

CURRENT SPEC:
{spec.model_dump_json(indent=2)}

CUSTOMER FEEDBACK:
{feedback}

Rules:
- Honor the feedback where it fits the existing six-page quoted scope.
- Do not invent facts to satisfy a request.
- Re-check the first-party website where a factual correction is needed.
- If a request requires unsupported claims, keep the claim out.
- Return a complete replacement WebsiteBuildSpec, not a patch.
""",
        ).final_output
        if not isinstance(revised, WebsiteBuildSpec):
            raise RuntimeError("Forge returned an unexpected revised build specification.")

        _set_agent(conn, "Nova", "WORKING", "Reviewing revised website UX")
        ux = Runner.run_sync(
            build_website_nova(),
            f"""
Review this revised website specification after customer feedback.

Customer: {project['business_name']}
Customer feedback: {feedback}

REVISED SPEC:
{revised.model_dump_json(indent=2)}

Approve only if the feedback was incorporated professionally without harming clarity,
credibility, mobile scannability or quotation conversion.
""",
        ).final_output
        if not isinstance(ux, UXReview):
            raise RuntimeError("Nova returned an unexpected revision review.")

        _set_agent(conn, "Sentinel", "WORKING", "QA reviewing website revision")
        qa = str(
            Runner.run_sync(
                build_sentinel(),
                f"""
Review this customer website revision before it replaces the staging build.

Customer: {project['business_name']}
Source website: {project['source_website']}
Customer feedback: {feedback}

REVISED SPEC:
{revised.model_dump_json(indent=2)}

NOVA REVIEW:
{ux.model_dump_json(indent=2)}

Return exactly:
STATUS: PASS
or
STATUS: FLAG

Then:
REASONS:
- concise bullets

REQUIRED_CHANGES:
- concise bullets, or "None"

PASS only if the revision remains inside the accepted six-page scope, does not introduce
invented claims/testimonials/results, and does not weaken customer ownership or launch safeguards.
""",
            ).final_output
        ).strip()

        if not _qa_passed(qa):
            _event(conn, args.project_id, "Sentinel", "REVISION_QA_FLAG", qa)
            _set_agent(conn, "Sentinel", "READY", "Revision blocked by QA")
            print("Revision was blocked by Sentinel. Existing staging build was left unchanged.")
            conn.close()
            return

        asset_dir = site_dir / "assets"
        logo_paths = sorted(p for p in asset_dir.glob("client-logo-*") if p.is_file())
        hero_paths = sorted(p for p in asset_dir.glob("client-hero-*") if p.is_file())
        product_paths = sorted(p for p in asset_dir.glob("client-product-*") if p.is_file())
        about_paths = sorted(p for p in asset_dir.glob("client-about-*") if p.is_file())

        legacy_images = [
            f"assets/{p.name}"
            for p in sorted(asset_dir.glob("customer-*"))
            if p.is_file()
        ]
        render_site(
            revised,
            site_dir,
            image_files=legacy_images,
            logo_file=f"assets/{logo_paths[0].name}" if logo_paths else None,
            hero_image=f"assets/{hero_paths[0].name}" if hero_paths else None,
            product_images=[f"assets/{p.name}" for p in product_paths],
            about_image=f"assets/{about_paths[0].name}" if about_paths else None,
        )
        errors = validate_site(site_dir)
        if errors:
            raise RuntimeError("Revised site validation failed: " + " | ".join(errors))

        spec_path.write_text(revised.model_dump_json(indent=2), encoding="utf-8")
        (project_root / "ux-review.json").write_text(
            ux.model_dump_json(indent=2), encoding="utf-8"
        )
        (project_root / "qa-report.txt").write_text(qa, encoding="utf-8")
        deploy_dir = export_deployment_package(project_root, site_dir)

        next_used = used + 1
        conn.execute(
            """UPDATE website_projects
            SET revision_rounds_used=?, customer_approval_status='PENDING',
                launch_approved=0, status='STAGING_READY', ux_review=?, qa_report=?, updated_at=?
            WHERE id=?""",
            (
                next_used,
                ux.model_dump_json(indent=2),
                qa,
                now_iso(),
                args.project_id,
            ),
        )
        conn.commit()
        _event(
            conn,
            args.project_id,
            "Forge",
            "REVISION_BUILT",
            f"Revision round {next_used} rendered and passed deterministic site validation.",
        )
        _set_agent(conn, "Forge", "READY", f"Revision round {next_used} complete")
        _set_agent(conn, "Nova", "READY", f"Revision UX score: {ux.score}/100")
        _set_agent(conn, "Sentinel", "READY", "Revision QA passed")

        print(f"\nRevision round {next_used}/2 complete.")
        print(f"Staging build updated: {site_dir}")
        print(f"Deploy package refreshed: {deploy_dir}")
        print("Customer approval reset to PENDING.")

        conn.close()
        if args.serve:
            serve_site(site_dir, args.project_id, max(1024, min(args.port, 65535)))

    except Exception as exc:
        try:
            _event(conn, args.project_id, "System", "REVISION_ERROR", str(exc)[:3000])
        finally:
            conn.close()
        raise


if __name__ == "__main__":
    main()
