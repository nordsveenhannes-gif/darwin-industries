from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from backend.agents.website_studio import WebsiteBuildSpec


REQUIRED_PAGES = [
    "index.html",
    "saunas.html",
    "ice-baths.html",
    "about.html",
    "faq.html",
    "contact.html",
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "website-project"


def _e(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _list(items: list[str], class_name: str = "detail-list") -> str:
    return "".join(f'<li>{_e(x)}</li>' for x in items)


def _product_cards(items) -> str:
    cards = []
    for item in items:
        details = _list(item.details[:5])
        cards.append(
            f"""
            <article class="product-card reveal">
              <div class="product-visual" aria-hidden="true">
                <span>{_e(item.eyebrow or "Signature collection")}</span>
              </div>
              <div class="product-copy">
                <p class="eyebrow">{_e(item.eyebrow)}</p>
                <h3>{_e(item.name)}</h3>
                <p>{_e(item.description)}</p>
                <ul class="detail-list">{details}</ul>
                <div class="product-footer">
                  <strong>{_e(item.price_label)}</strong>
                  <a class="text-link" href="contact.html">Request a quote →</a>
                </div>
              </div>
            </article>
            """
        )
    return "".join(cards)


def _nav(current: str) -> str:
    links = [
        ("index.html", "Home"),
        ("saunas.html", "Saunas"),
        ("ice-baths.html", "Ice Baths"),
        ("about.html", "About"),
        ("faq.html", "FAQ"),
    ]
    html = []
    for href, label in links:
        active = ' aria-current="page"' if href == current else ""
        html.append(f'<a href="{href}"{active}>{label}</a>')
    return "".join(html)


def _layout(
    spec: WebsiteBuildSpec,
    current: str,
    title: str,
    description: str,
    body: str,
) -> str:
    brand = _e(spec.brand_name)
    canonical_hint = _e(spec.website_url.rstrip("/"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta name="theme-color" content="#11100e">
  <title>{_e(title)} | {brand}</title>
  <meta name="description" content="{_e(description)}">
  <meta property="og:title" content="{_e(title)} | {brand}">
  <meta property="og:description" content="{_e(description)}">
  <meta property="og:type" content="website">
  <meta name="darwin-source-site" content="{canonical_hint}">
  <link rel="stylesheet" href="assets/styles.css">
  <script defer src="assets/app.js"></script>
</head>
<body data-page="{_e(current)}">
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="site-header">
    <a class="brand" href="index.html" aria-label="{brand} home">
      <span class="brand-mark" aria-hidden="true">F<span>+</span>I</span>
      <span>{brand}</span>
    </a>
    <button class="menu-button" type="button" aria-expanded="false" aria-controls="site-nav">
      <span></span><span></span><span></span><span class="sr-only">Menu</span>
    </button>
    <nav id="site-nav" class="site-nav" aria-label="Main navigation">
      {_nav(current)}
      <a class="nav-cta" href="contact.html">Get pricing</a>
    </nav>
  </header>

  <main id="main">{body}</main>

  <footer class="site-footer">
    <div>
      <a class="brand footer-brand" href="index.html">
        <span class="brand-mark" aria-hidden="true">F<span>+</span>I</span>
        <span>{brand}</span>
      </a>
      <p class="footer-note">Premium hot and cold wellbeing equipment. Staging rebuild prepared by Darwin Industries.</p>
    </div>
    <div class="footer-links">
      <a href="saunas.html">Saunas</a>
      <a href="ice-baths.html">Ice Baths</a>
      <a href="faq.html">FAQ</a>
      <a href="contact.html">Get pricing</a>
    </div>
    <div>
      <p class="eyebrow">Staging notice</p>
      <p class="footer-note">This preview is not the live customer website. Final claims, photography, legal pages and domain launch require customer approval.</p>
    </div>
  </footer>
</body>
</html>
"""


def _home(spec: WebsiteBuildSpec) -> str:
    trust = "".join(
        f'<div class="trust-item"><span>{i:02d}</span><p>{_e(point)}</p></div>'
        for i, point in enumerate(spec.trust_points[:4], 1)
    )
    sauna_name = spec.saunas[0].name if spec.saunas else "Infrared saunas"
    ice_name = spec.ice_baths[0].name if spec.ice_baths else "Ice baths"
    return f"""
<section class="hero">
  <div class="hero-copy reveal">
    <p class="eyebrow">{_e(spec.hero_eyebrow)}</p>
    <h1>{_e(spec.hero_heading)}</h1>
    <p class="lede">{_e(spec.hero_subheading)}</p>
    <div class="button-row">
      <a class="button button-primary" href="contact.html">Get pricing</a>
      <a class="button button-ghost" href="#collections">Explore collections</a>
    </div>
  </div>
  <div class="hero-art reveal" aria-label="Abstract fire and ice visual">
    <div class="orb orb-fire"></div>
    <div class="orb orb-ice"></div>
    <div class="glass-card">
      <span>FIRE</span>
      <strong>Warmth, crafted.</strong>
      <hr>
      <span>ICE</span>
      <strong>Cold, refined.</strong>
    </div>
  </div>
</section>

<section class="trust-strip" aria-label="Why choose us">{trust}</section>

<section id="collections" class="section">
  <div class="section-heading reveal">
    <p class="eyebrow">Two disciplines. One ritual.</p>
    <h2>Build a private wellbeing space around the way you want to feel.</h2>
  </div>
  <div class="collection-grid">
    <a class="collection collection-fire reveal" href="saunas.html">
      <span class="eyebrow">Fire / Infrared</span>
      <h3>{_e(sauna_name)}</h3>
      <p>{_e(spec.sauna_intro)}</p>
      <span class="text-link">Explore saunas →</span>
    </a>
    <a class="collection collection-ice reveal" href="ice-baths.html">
      <span class="eyebrow">Ice / Cold immersion</span>
      <h3>{_e(ice_name)}</h3>
      <p>{_e(spec.ice_bath_intro)}</p>
      <span class="text-link">Explore ice baths →</span>
    </a>
  </div>
</section>

<section class="statement">
  <p class="eyebrow">Designed around the product</p>
  <blockquote>{_e(spec.positioning)}</blockquote>
  <a class="button button-primary" href="contact.html">Discuss your space</a>
</section>
"""


def _products_page(spec: WebsiteBuildSpec, kind: str) -> str:
    if kind == "saunas":
        title = "Infrared saunas"
        intro = spec.sauna_intro
        items = spec.saunas
        tone = "fire"
    else:
        title = "Ice baths"
        intro = spec.ice_bath_intro
        items = spec.ice_baths
        tone = "ice"
    return f"""
<section class="page-hero page-hero-{tone}">
  <p class="eyebrow">{_e(kind.replace("-", " ").title())}</p>
  <h1>{_e(title)}</h1>
  <p class="lede">{_e(intro)}</p>
  <a class="button button-primary" href="contact.html">Request pricing</a>
</section>
<section class="section">
  <div class="section-heading">
    <p class="eyebrow">Collection</p>
    <h2>Choose the format that fits your space.</h2>
  </div>
  <div class="product-grid">{_product_cards(items)}</div>
</section>
<section class="cta-band">
  <div><p class="eyebrow">Need help choosing?</p><h2>Tell us about your room, preferred finish and timeline.</h2></div>
  <a class="button button-light" href="contact.html">Start an enquiry</a>
</section>
"""


def _about(spec: WebsiteBuildSpec) -> str:
    trust = "".join(f"<li>{_e(x)}</li>" for x in spec.trust_points)
    return f"""
<section class="page-hero">
  <p class="eyebrow">About</p>
  <h1>{_e(spec.about_heading)}</h1>
  <p class="lede">{_e(spec.about_body)}</p>
</section>
<section class="section two-col">
  <div class="reveal">
    <p class="eyebrow">Our approach</p>
    <h2>Premium equipment should be clear to buy and straightforward to own.</h2>
  </div>
  <div class="prose reveal">
    <p>{_e(spec.positioning)}</p>
    <ul class="feature-list">{trust}</ul>
  </div>
</section>
<section class="cta-band">
  <div><p class="eyebrow">Planning a project?</p><h2>Share your space and we’ll help narrow the options.</h2></div>
  <a class="button button-light" href="contact.html">Get pricing</a>
</section>
"""


def _faq(spec: WebsiteBuildSpec) -> str:
    items = "".join(
        f"""
        <details class="faq-item reveal">
          <summary>{_e(item.question)}</summary>
          <div><p>{_e(item.answer)}</p></div>
        </details>
        """
        for item in spec.faqs
    )
    return f"""
<section class="page-hero">
  <p class="eyebrow">FAQ</p>
  <h1>Useful answers before you request a quote.</h1>
  <p class="lede">A concise guide to product choices, delivery, customisation and the quotation process.</p>
</section>
<section class="section faq-wrap">{items}</section>
"""


def _contact(spec: WebsiteBuildSpec) -> str:
    address = "<br>".join(_e(x) for x in spec.address_lines)
    contact_bits = []
    if spec.contact_email:
        contact_bits.append(f'<a href="mailto:{_e(spec.contact_email)}">{_e(spec.contact_email)}</a>')
    if spec.contact_phone:
        contact_bits.append(f'<a href="tel:{_e(spec.contact_phone)}">{_e(spec.contact_phone)}</a>')
    contacts = "<br>".join(contact_bits)
    return f"""
<section class="page-hero">
  <p class="eyebrow">Get pricing</p>
  <h1>Tell us what you’re building.</h1>
  <p class="lede">Share the product, room and timing you have in mind. This staging form works locally and records the enquiry in Darwin’s project database.</p>
</section>
<section class="section contact-grid">
  <div class="contact-copy reveal">
    <p class="eyebrow">Project enquiry</p>
    <h2>Start with the essentials.</h2>
    <p>We’ll use your details to prepare the right product conversation. No fake urgency, no automatic purchase and no hidden checkout.</p>
    <div class="contact-details">
      {f'<p><strong>Business address</strong><br>{address}</p>' if address else ''}
      {f'<p><strong>Contact</strong><br>{contacts}</p>' if contacts else ''}
    </div>
  </div>
  <form id="quote-form" class="quote-form reveal" novalidate>
    <div class="field-row">
      <label>First name<input name="name" autocomplete="name" required maxlength="80"></label>
      <label>Email<input type="email" name="email" autocomplete="email" required maxlength="160"></label>
    </div>
    <label>Product interest
      <select name="interest" required>
        <option value="">Choose one</option>
        <option>Infrared sauna</option>
        <option>Ice bath</option>
        <option>Sauna + ice bath</option>
        <option>Commercial / bespoke project</option>
      </select>
    </label>
    <label>Project notes<textarea name="message" rows="6" required maxlength="2000" placeholder="Room, preferred finish, location and desired timeline"></textarea></label>
    <label class="consent"><input type="checkbox" name="consent" required> <span>I’m happy to be contacted about this quotation request.</span></label>
    <button class="button button-primary" type="submit">Send enquiry</button>
    <p id="form-status" class="form-status" role="status" aria-live="polite"></p>
  </form>
</section>
"""


STYLES = r"""
:root{
  --ink:#171512;--paper:#f4f0e8;--cream:#ebe4d8;--line:rgba(23,21,18,.14);
  --fire:#9e3d22;--ice:#366575;--dark:#11100e;--white:#fff;--muted:#6e6a62;
  --radius:22px;--shadow:0 28px 70px rgba(17,16,14,.12);
}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}
a{color:inherit;text-decoration:none}img{max-width:100%;display:block}button,input,select,textarea{font:inherit}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.skip-link{position:fixed;left:16px;top:-100px;z-index:50;background:#fff;padding:10px 14px;border-radius:8px}.skip-link:focus{top:16px}
.site-header{height:82px;padding:0 clamp(20px,5vw,72px);display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:rgba(244,240,232,.88);backdrop-filter:blur(18px);position:sticky;top:0;z-index:20}
.brand{display:flex;align-items:center;gap:12px;font-weight:650;letter-spacing:.04em}.brand-mark{font-family:Georgia,serif;font-size:22px}.brand-mark span{color:var(--fire)}
.site-nav{display:flex;align-items:center;gap:28px;font-size:13px}.site-nav a{opacity:.75}.site-nav a:hover,.site-nav a[aria-current="page"]{opacity:1}.nav-cta{border:1px solid var(--ink);border-radius:999px;padding:10px 16px;opacity:1!important}
.menu-button{display:none;border:0;background:none;padding:8px}.menu-button span:not(.sr-only){display:block;width:24px;height:1px;background:var(--ink);margin:5px}
.hero{min-height:calc(100vh - 82px);display:grid;grid-template-columns:1.05fr .95fr;align-items:center;gap:5vw;padding:clamp(56px,8vw,120px) clamp(20px,7vw,110px)}
.hero-copy{max-width:760px}.eyebrow{text-transform:uppercase;letter-spacing:.18em;font-size:11px;font-weight:750;margin:0 0 18px;color:var(--muted)}
h1,h2,h3,blockquote{font-family:Georgia,"Times New Roman",serif;font-weight:400;letter-spacing:-.035em;margin-top:0}h1{font-size:clamp(54px,7.2vw,112px);line-height:.92;margin-bottom:30px}h2{font-size:clamp(38px,5vw,70px);line-height:1.02}h3{font-size:32px;line-height:1.05}.lede{font-size:clamp(18px,2vw,24px);max-width:680px;color:#565149}
.button-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:34px}.button{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;padding:14px 22px;font-size:13px;font-weight:700;transition:.2s transform,.2s background}.button:hover{transform:translateY(-2px)}.button-primary{background:var(--ink);color:#fff}.button-ghost{border:1px solid var(--line)}.button-light{background:#fff;color:var(--dark)}
.hero-art{position:relative;min-height:580px;border-radius:36px;background:#171512;overflow:hidden;box-shadow:var(--shadow)}.orb{position:absolute;border-radius:50%;filter:blur(3px)}.orb-fire{width:440px;height:440px;background:radial-gradient(circle at 35% 35%,#f3b468 0,#a84125 45%,rgba(168,65,37,0) 72%);left:-90px;top:-40px}.orb-ice{width:480px;height:480px;background:radial-gradient(circle at 50% 40%,#9ccbd2 0,#3d7485 42%,rgba(61,116,133,0) 72%);right:-120px;bottom:-110px}.glass-card{position:absolute;inset:auto 9% 9% 9%;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);backdrop-filter:blur(20px);color:#fff;padding:28px;border-radius:24px;display:grid;grid-template-columns:90px 1fr;gap:10px 20px}.glass-card hr{grid-column:1/-1;width:100%;border:0;border-top:1px solid rgba(255,255,255,.15)}.glass-card span{font-size:10px;letter-spacing:.2em}.glass-card strong{font-family:Georgia,serif;font-size:24px;font-weight:400}
.trust-strip{display:grid;grid-template-columns:repeat(4,1fr);border-block:1px solid var(--line)}.trust-item{padding:30px clamp(20px,3vw,44px);border-right:1px solid var(--line);display:flex;gap:18px}.trust-item:last-child{border-right:0}.trust-item span{font-size:10px;color:var(--muted)}.trust-item p{margin:0;font-size:13px}
.section{padding:clamp(76px,10vw,150px) clamp(20px,7vw,110px)}.section-heading{max-width:980px;margin-bottom:56px}.collection-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.collection{min-height:540px;padding:48px;border-radius:var(--radius);display:flex;flex-direction:column;justify-content:flex-end;color:#fff;overflow:hidden;position:relative}.collection:before{content:"";position:absolute;inset:0;opacity:.85}.collection>*{position:relative;z-index:1}.collection h3{font-size:clamp(42px,5vw,72px);max-width:600px;margin-bottom:18px}.collection p{max-width:600px}.collection-fire{background:radial-gradient(circle at 70% 5%,#bc6548,#542319 58%,#1b1310)}.collection-ice{background:radial-gradient(circle at 70% 5%,#7aabba,#294e5c 58%,#111a1e)}.collection .eyebrow{color:rgba(255,255,255,.68)}.text-link{font-size:13px;font-weight:750;margin-top:20px}
.statement{padding:clamp(90px,13vw,190px) clamp(20px,10vw,160px);background:var(--dark);color:#fff}.statement .eyebrow{color:#a8a198}.statement blockquote{font-size:clamp(42px,6vw,86px);line-height:1.03;max-width:1200px;margin:0 0 42px}
.page-hero{padding:clamp(90px,12vw,170px) clamp(20px,10vw,150px) 80px}.page-hero h1{max-width:1050px}.page-hero-fire{background:linear-gradient(145deg,#f4f0e8 45%,#dfc3ad)}.page-hero-ice{background:linear-gradient(145deg,#f4f0e8 45%,#c9dde1)}
.product-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}.product-card{background:#fff;border-radius:var(--radius);overflow:hidden;box-shadow:0 10px 30px rgba(17,16,14,.05)}.product-visual{height:280px;padding:28px;display:flex;align-items:flex-end;background:linear-gradient(135deg,#28241f,#9e5d43 48%,#628491);color:#fff}.product-visual span{font-size:10px;text-transform:uppercase;letter-spacing:.2em}.product-copy{padding:34px}.product-copy p{color:#5f5a52}.detail-list{padding-left:18px;color:#4f4a43}.detail-list li{margin:7px 0}.product-footer{border-top:1px solid var(--line);margin-top:28px;padding-top:20px;display:flex;justify-content:space-between;gap:20px;font-size:13px}
.cta-band{margin:0 clamp(20px,4vw,60px) clamp(20px,4vw,60px);background:var(--dark);color:#fff;border-radius:32px;padding:clamp(42px,6vw,76px);display:flex;align-items:end;justify-content:space-between;gap:30px}.cta-band h2{max-width:900px;margin-bottom:0}.cta-band .eyebrow{color:#aaa49b}
.two-col{display:grid;grid-template-columns:.9fr 1.1fr;gap:8vw}.prose{font-size:19px;color:#504b44}.feature-list{list-style:none;padding:0;margin-top:36px;border-top:1px solid var(--line)}.feature-list li{padding:16px 0;border-bottom:1px solid var(--line)}
.faq-wrap{max-width:1050px;margin:auto}.faq-item{border-top:1px solid var(--line)}.faq-item:last-child{border-bottom:1px solid var(--line)}.faq-item summary{cursor:pointer;list-style:none;padding:26px 0;font-family:Georgia,serif;font-size:25px}.faq-item summary::-webkit-details-marker{display:none}.faq-item summary:after{content:"+";float:right;font-family:Inter,sans-serif}.faq-item[open] summary:after{content:"−"}.faq-item div{padding:0 0 26px;max-width:800px;color:#5d5850}
.contact-grid{display:grid;grid-template-columns:.85fr 1.15fr;gap:8vw;align-items:start}.contact-copy{position:sticky;top:130px}.contact-details{margin-top:36px}.contact-details a{text-decoration:underline}.quote-form{background:#fff;padding:clamp(28px,4vw,52px);border-radius:var(--radius);box-shadow:var(--shadow)}.quote-form label{display:grid;gap:8px;font-size:12px;font-weight:700;margin-bottom:20px}.quote-form input,.quote-form select,.quote-form textarea{width:100%;border:1px solid #d6d0c6;border-radius:12px;padding:14px 15px;background:#fbfaf7;color:var(--ink)}.quote-form input:focus,.quote-form select:focus,.quote-form textarea:focus{outline:2px solid #6f8991;outline-offset:2px}.field-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}.consent{display:flex!important;grid-template-columns:auto 1fr!important;align-items:flex-start}.consent input{width:auto;margin-top:4px}.form-status{min-height:24px;font-size:13px}.form-status.success{color:#17653a}.form-status.error{color:#a12b2b}
.site-footer{background:#0f0e0c;color:#fff;padding:64px clamp(20px,6vw,90px);display:grid;grid-template-columns:1.3fr .6fr 1fr;gap:50px}.footer-brand{margin-bottom:20px}.footer-note{color:#aaa49b;max-width:480px;font-size:12px}.footer-links{display:grid;gap:10px;font-size:13px}.site-footer .eyebrow{color:#aaa49b}
.reveal{animation:fadeUp .7s ease both}@keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
@media(max-width:900px){
  .site-header{height:70px}.menu-button{display:block}.site-nav{display:none;position:absolute;top:70px;left:0;right:0;background:var(--paper);padding:24px;box-shadow:0 18px 40px rgba(0,0,0,.08);flex-direction:column;align-items:flex-start}.site-nav.open{display:flex}
  .hero{grid-template-columns:1fr;padding-top:70px}.hero-art{min-height:440px}.trust-strip{grid-template-columns:1fr 1fr}.trust-item:nth-child(2){border-right:0}.trust-item{border-bottom:1px solid var(--line)}
  .collection-grid,.product-grid,.two-col,.contact-grid{grid-template-columns:1fr}.collection{min-height:440px}.contact-copy{position:static}.site-footer{grid-template-columns:1fr}.cta-band{align-items:flex-start;flex-direction:column}
}
@media(max-width:560px){h1{font-size:48px}.hero-art{min-height:360px}.glass-card{grid-template-columns:60px 1fr;padding:20px}.trust-strip{grid-template-columns:1fr}.trust-item{border-right:0}.collection{padding:30px;min-height:400px}.product-grid{grid-template-columns:1fr}.field-row{grid-template-columns:1fr}.product-footer{flex-direction:column}}
"""


APP_JS = r"""
(() => {
  const button = document.querySelector('.menu-button');
  const nav = document.querySelector('#site-nav');
  if (button && nav) {
    button.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  const form = document.querySelector('#quote-form');
  const status = document.querySelector('#form-status');
  if (!form || !status) return;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    status.className = 'form-status';
    status.textContent = '';

    if (!form.reportValidity()) return;

    const data = Object.fromEntries(new FormData(form).entries());
    data.consent = Boolean(data.consent);

    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Sending…';

    try {
      const response = await fetch('/api/quote', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to send your enquiry.');
      status.classList.add('success');
      status.textContent = 'Thank you — your enquiry has been recorded for this staging project.';
      form.reset();
    } catch (error) {
      status.classList.add('error');
      status.textContent = error.message || 'Something went wrong. Please try again.';
    } finally {
      submit.disabled = false;
      submit.textContent = 'Send enquiry';
    }
  });
})();
"""


def render_site(spec: WebsiteBuildSpec, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = output_dir / "assets"
    assets.mkdir(exist_ok=True)

    pages = {
        "index.html": (
            "Premium wellness equipment",
            spec.hero_subheading,
            _home(spec),
        ),
        "saunas.html": (
            "Infrared saunas",
            spec.sauna_intro,
            _products_page(spec, "saunas"),
        ),
        "ice-baths.html": (
            "Premium ice baths",
            spec.ice_bath_intro,
            _products_page(spec, "ice-baths"),
        ),
        "about.html": (
            "About",
            spec.about_body,
            _about(spec),
        ),
        "faq.html": (
            "Frequently asked questions",
            "Answers about products, delivery, customisation and quotations.",
            _faq(spec),
        ),
        "contact.html": (
            "Get pricing",
            "Request pricing and discuss your Fire & Ice wellbeing project.",
            _contact(spec),
        ),
    }

    for filename, (title, description, body) in pages.items():
        (output_dir / filename).write_text(
            _layout(spec, filename, title, description, body),
            encoding="utf-8",
        )

    (assets / "styles.css").write_text(STYLES, encoding="utf-8")
    (assets / "app.js").write_text(APP_JS, encoding="utf-8")
    (output_dir / "robots.txt").write_text(
        "User-agent: *\nDisallow: /\n",
        encoding="utf-8",
    )
    (output_dir / "build.json").write_text(
        json.dumps(
            {
                "brand": spec.brand_name,
                "source_website": spec.website_url,
                "staging": True,
                "pages": REQUIRED_PAGES,
                "unverified_claims": spec.unverified_claims,
                "customer_assets_needed": spec.customer_assets_needed,
                "evidence_urls": spec.evidence_urls,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def validate_site(output_dir: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_PAGES:
        path = output_dir / name
        if not path.exists():
            errors.append(f"Missing page: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        if "<title>" not in text or "<main" not in text:
            errors.append(f"Malformed document structure: {name}")
        if 'name="robots" content="noindex,nofollow"' not in text:
            errors.append(f"Staging noindex missing: {name}")

    for name in ["assets/styles.css", "assets/app.js", "build.json", "robots.txt"]:
        if not (output_dir / name).exists():
            errors.append(f"Missing asset: {name}")

    contact = output_dir / "contact.html"
    if contact.exists():
        text = contact.read_text(encoding="utf-8")
        if 'id="quote-form"' not in text or "/api/quote" not in APP_JS:
            errors.append("Functional quote form wiring missing")

    # Verify internal .html links point to generated pages.
    generated = {p.name for p in output_dir.glob("*.html")}
    link_pattern = re.compile(r'href="([^"]+\.html)(?:#[^"]*)?"')
    for page in output_dir.glob("*.html"):
        for href in link_pattern.findall(page.read_text(encoding="utf-8")):
            target = Path(urlparse(href).path).name
            if target and target not in generated:
                errors.append(f"Broken internal link in {page.name}: {href}")

    return sorted(set(errors))
