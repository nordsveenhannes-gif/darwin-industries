from __future__ import annotations

import json
from html import escape
from pathlib import Path


def render_emergency_staging(
    output_dir: Path,
    *,
    brand_name: str,
    source_website: str,
    reason: str,
) -> None:
    """Render a conservative noindex staging shell when the normal renderer cannot validate.

    This is a continuity fallback, not a public-launch bypass. It deliberately strips
    disputed claims, integrations and risky content while preserving a reviewable site.
    """
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)

    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    safe_brand = escape(brand_name or "Website project")
    safe_source = escape(source_website or "")
    pages = [
        "index.html",
        "services.html",
        "projects.html",
        "about.html",
        "faq.html",
        "contact.html",
        "privacy.html",
        "404.html",
    ]

    css = """
:root{--bg:#f4f1eb;--ink:#151319;--card:#fff;--muted:#6d6873;--line:#ddd6df;--accent:#292331}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}
header,main,footer{width:min(1120px,calc(100% - 36px));margin:auto}header{padding:28px 0;display:flex;justify-content:space-between;gap:24px;align-items:center}
nav{display:flex;gap:18px;flex-wrap:wrap}a{color:inherit}.brand{font-weight:900}.hero{padding:90px 0 70px}.eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);font-weight:800}
h1{font:600 clamp(46px,8vw,92px)/.95 Georgia,serif;letter-spacing:-.045em;max-width:920px}h2{font:500 clamp(30px,5vw,54px)/1 Georgia,serif}
.lede{font-size:20px;color:var(--muted);max-width:760px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;padding:20px 0 80px}
.card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:30px;min-height:220px}.notice{border-left:4px solid var(--accent);padding:18px 20px;background:#ebe6ee;margin:25px 0}
form{display:grid;gap:16px;background:#fff;padding:28px;border-radius:20px;border:1px solid var(--line)}label{display:grid;gap:7px;font-weight:700}
input,select,textarea{font:inherit;padding:13px;border:1px solid #cfc7d2;border-radius:10px}button{border:0;border-radius:999px;background:var(--ink);color:white;padding:13px 20px;font-weight:800;cursor:pointer}
footer{padding:42px 0 60px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
@media(max-width:720px){header{align-items:flex-start;flex-direction:column}.grid{grid-template-columns:1fr}.hero{padding-top:55px}}
"""
    js = """
(() => {
 const form=document.querySelector('#quote-form'); if(!form)return;
 const status=document.querySelector('#form-status');
 form.addEventListener('submit',async(e)=>{
  e.preventDefault(); if(!form.reportValidity())return;
  const data=Object.fromEntries(new FormData(form).entries());data.consent=Boolean(data.consent);
  try{
   const r=await fetch('/api/quote',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
   const x=await r.json();if(!r.ok)throw new Error(x.error||'Unable to send enquiry.');
   status.textContent='Thank you — your enquiry was recorded.';form.reset();
  }catch(err){status.textContent=err.message||'Unable to send enquiry.'}
 });
})();
"""
    favicon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#151319"/><text x="32" y="41" text-anchor="middle" font-family="Georgia,serif" font-size="28" fill="#fff">S</text></svg>"""
    (assets / "styles.css").write_text(css, encoding="utf-8")
    (assets / "app.js").write_text(js, encoding="utf-8")
    (assets / "favicon.svg").write_text(favicon, encoding="utf-8")
    (output_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    nav = (
        '<nav><a href="index.html">Home</a><a href="services.html">Services</a>'
        '<a href="projects.html">Projects</a><a href="about.html">About</a>'
        '<a href="faq.html">FAQ</a><a href="contact.html">Get pricing</a></nav>'
    )

    def shell(title: str, body: str) -> str:
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{escape(title)} · {safe_brand}</title>
<link rel="icon" href="assets/favicon.svg"><link rel="stylesheet" href="assets/styles.css"></head>
<body><header><div class="brand">{safe_brand}</div>{nav}</header><main>{body}</main>
<footer>Private staging preview. Unverified or unsafe claims and integrations have been deliberately omitted pending final production verification.</footer>
<script src="assets/app.js"></script></body></html>"""

    home = f"""<section class="hero"><p class="eyebrow">Private staging concept</p>
<h1>A clean, credible foundation for {safe_brand}.</h1>
<p class="lede">This conservative preview keeps the customer journey moving while disputed claims, unsafe integrations and unverified details stay quarantined from the page.</p>
<div class="notice"><strong>Staging safe mode:</strong> the design system recovered automatically from a build/QA fault. This preview is intentionally factual and minimal rather than inventing missing information.</div></section>
<section class="grid"><article class="card"><p class="eyebrow">01</p><h2>Clear offer</h2><p>Give visitors a fast path to understand the business and what to do next.</p></article>
<article class="card"><p class="eyebrow">02</p><h2>Get pricing</h2><p>Use the enquiry flow to capture serious customer intent without fabricated promises.</p></article></section>"""
    services = """<section class="hero"><p class="eyebrow">Services</p><h1>What we can help with.</h1><p class="lede">Service details that could not be safely verified are intentionally withheld from this recovery preview.</p></section>"""
    projects = """<section class="hero"><p class="eyebrow">Projects</p><h1>Work worth discussing.</h1><p class="lede">No fake case studies, testimonials or results are shown. Customer-approved project material can be added during review.</p></section>"""
    about = f"""<section class="hero"><p class="eyebrow">About</p><h1>{safe_brand}</h1><p class="lede">This private concept uses only a restrained business description until the customer approves richer factual copy.</p>{f'<p>Existing public source: {safe_source}</p>' if safe_source else ''}</section>"""
    faq = """<section class="hero"><p class="eyebrow">FAQ</p><h1>Useful questions, without invented answers.</h1><p class="lede">Commercial, legal, warranty and technical facts that were not verified are left for final customer confirmation instead of being guessed.</p></section>"""
    privacy = """<section class="hero"><p class="eyebrow">Staging privacy</p><h1>Private preview only.</h1><p class="lede">This is not final legal text. Production privacy, cookies, analytics and processors must be configured from verified customer information before public launch.</p></section>"""
    contact = """<section class="hero"><p class="eyebrow">Get pricing</p><h1>Tell us about your project.</h1><p class="lede">This staging form records a test enquiry through the local staging backend.</p></section>
<section class="grid"><form id="quote-form"><label>Name<input name="name" required></label><label>Email<input name="email" type="email" required></label>
<label>Interest<select name="interest" required><option value="">Choose one</option><option>Website enquiry</option><option>Project pricing</option><option>Other</option></select></label>
<label>Message<textarea name="message" rows="5" required></textarea></label><label><span><input type="checkbox" name="consent" required> I agree to be contacted about this enquiry.</span></label>
<input name="company" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px"><button type="submit">Send enquiry</button><p id="form-status"></p></form>
<article class="card"><h2>What happens next</h2><p>The team reviews the enquiry and responds using customer-approved contact details and processes.</p></article></section>"""
    not_found = """<section class="hero"><p class="eyebrow">404</p><h1>That page wandered off.</h1><p class="lede"><a href="index.html">Return home.</a></p></section>"""

    payloads = {
        "index.html": ("Home", home),
        "services.html": ("Services", services),
        "projects.html": ("Projects", projects),
        "about.html": ("About", about),
        "faq.html": ("FAQ", faq),
        "contact.html": ("Get pricing", contact),
        "privacy.html": ("Privacy", privacy),
        "404.html": ("Not found", not_found),
    }
    for filename, (title, body) in payloads.items():
        (output_dir / filename).write_text(shell(title, body), encoding="utf-8")

    (output_dir / "build.json").write_text(
        json.dumps(
            {
                "brand": brand_name,
                "source_website": source_website,
                "staging": True,
                "recovery_mode": True,
                "recovery_reason": reason[:2000],
                "pages": pages,
                "collections": ["Services", "Projects"],
                "unverified_claims": ["Recovery mode removed unverified/risky content."],
                "customer_assets_needed": [],
                "evidence_urls": [source_website] if source_website else [],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
