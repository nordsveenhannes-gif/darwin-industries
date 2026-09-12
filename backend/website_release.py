from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin

from backend.storage import connect, init_db, now_iso


def _canonical_path(filename: str) -> str:
    if filename == "index.html":
        return ""
    if filename.endswith(".html"):
        return filename[:-5] + "/"
    return filename


def _make_release(project_root: Path, domain: str) -> Path:
    deploy_dir = project_root / "deploy"
    source_site = deploy_dir / "site"
    if not source_site.exists():
        raise RuntimeError("Deployable staging site is missing.")

    release_dir = project_root / "release"
    release_site = release_dir / "site"
    if release_dir.exists():
        shutil.rmtree(release_dir)
    shutil.copytree(deploy_dir, release_dir)

    base = domain.rstrip("/") + "/"
    sitemap_urls: list[str] = []

    for page in sorted(release_site.glob("*.html")):
        text = page.read_text(encoding="utf-8")
        if page.name == "404.html":
            # Error pages should remain out of search indexes.
            text = text.replace(
                'name="robots" content="noindex,nofollow"',
                'name="robots" content="noindex,follow"',
            )
        else:
            text = text.replace(
                'name="robots" content="noindex,nofollow"',
                'name="robots" content="index,follow"',
            )
            canonical = urljoin(base, _canonical_path(page.name))
            canonical_tag = f'<link rel="canonical" href="{canonical}">'
            if canonical_tag not in text:
                text = text.replace("</title>", f"</title>\n  {canonical_tag}", 1)
            sitemap_urls.append(canonical)
        page.write_text(text, encoding="utf-8")

    (release_site / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: " + urljoin(base, "sitemap.xml") + "\n",
        encoding="utf-8",
    )
    sitemap = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in sitemap_urls:
        sitemap.append(f"  <url><loc>{url}</loc></url>")
    sitemap.append("</urlset>")
    (release_site / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")

    launch_notes = """# Production release package

This package was created only after Darwin's explicit release gates were recorded.

Before changing DNS or replacing the live site:
- verify the approved domain and HTTPS,
- test the production enquiry destination end to end,
- implement and test the agreed old-URL to new-URL redirect map,
- verify privacy/cookie behavior against the actual production tools,
- confirm analytics/Search Console tracking if required,
- verify sitemap.xml, robots.txt and canonical URLs,
- take a backup of the old site and document rollback,
- run desktop/mobile/keyboard/form/link/404 checks,
- obtain the customer's final launch-window confirmation.

This folder is a release artifact. Creating it does not itself deploy or modify DNS.
"""
    (release_dir / "LAUNCH_NOTES.md").write_text(launch_notes, encoding="utf-8")
    return release_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an indexable production release package after all Darwin launch gates pass."
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--domain", required=True, help="Final public origin, e.g. https://example.com")
    args = parser.parse_args()

    domain = args.domain.strip()
    if not re.match(r"^https://[A-Za-z0-9.-]+(?::\d+)?/?$", domain):
        raise SystemExit("Use the final HTTPS origin only, e.g. https://www.example.com")

    conn = connect()
    init_db(conn)
    project = conn.execute(
        "SELECT * FROM website_projects WHERE id=?", (args.project_id,)
    ).fetchone()
    if not project:
        raise SystemExit(f"Website project #{args.project_id} does not exist.")
    if project["mode"] != "CUSTOMER":
        raise SystemExit("Demo projects cannot produce a production release package.")
    if project["status"] != "RELEASE_READY" or not project["launch_approved"]:
        raise SystemExit(
            "Release blocked: explicit launch approval and all production gates must be complete first."
        )

    project_root = Path(project["build_dir"])
    release_dir = _make_release(project_root, domain)

    conn.execute(
        "UPDATE website_projects SET status='RELEASE_PACKAGE_READY',updated_at=? WHERE id=?",
        (now_iso(), args.project_id),
    )
    conn.execute(
        """INSERT INTO website_project_events(project_id,agent,stage,detail,created_at)
        VALUES(?,?,?,?,?)""",
        (
            args.project_id,
            "Sentinel",
            "RELEASE_PACKAGE_READY",
            f"Production release package created for {domain}. No deployment or DNS change was performed.",
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()

    print(f"\nProduction release package ready: {release_dir}")
    print(f"Target domain: {domain}")
    print("Staging noindex blocks were removed only from this release copy.")
    print("No public deployment or DNS change was performed.")


if __name__ == "__main__":
    main()
