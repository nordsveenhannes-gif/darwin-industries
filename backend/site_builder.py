from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from backend.agents.website_studio import CollectionSpec, WebsiteBuildSpec


BASE_REQUIRED_PAGES = ["index.html", "about.html", "faq.html", "contact.html", "privacy.html", "404.html"]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "website-project"


def _e(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _list(items: list[str]) -> str:
    return "".join(f'<li>{_e(x)}</li>' for x in items)


def _brand_mark(name: str) -> str:
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    initials = [w[0].upper() for w in words[:2]]
    if not initials:
        return "D"
    return '<span>+</span>'.join(_e(x) for x in initials)


def _collection_entries(spec: WebsiteBuildSpec):
    reserved = {"index", "about", "faq", "contact", "privacy"}
    used = set()
    entries = []
    for index, collection in enumerate(spec.collections[:2], 1):
        base = slugify(collection.name)
        if base in reserved:
            base = f"{base}-collection"
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        entries.append((collection, f"{candidate}.html", index))
    return entries


def _product_cards(items, images: list[str] | None = None, offset: int = 0) -> str:
    cards = []
    images = images or []
    for index, item in enumerate(items):
        details = _list(item.details[:5])
        image_index = offset + index
        if image_index < len(images):
            image = _e(images[image_index])
            visual = (
                f'<div class="product-visual product-photo" '
                f'style="background-image:linear-gradient(180deg,rgba(17,16,14,.05),rgba(17,16,14,.45)),url(&quot;{image}&quot;)" '
                f'aria-label="{_e(item.name)} product image">'
                f'<span>{_e(item.eyebrow or "Signature collection")}</span></div>'
            )
        else:
            visual = (
                f'<div class="product-visual" aria-hidden="true">'
                f'<span>{_e(item.eyebrow or "Signature collection")}</span></div>'
            )
        cards.append(
            f"""
            <article class="product-card reveal">
              {visual}
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


def _nav(spec: WebsiteBuildSpec, current: str) -> str:
    links = [("index.html", "Home")]
    links.extend((filename, collection.name) for collection, filename, _ in _collection_entries(spec))
    links.extend([("about.html", "About"), ("faq.html", "FAQ")])
    html = []
    for href, label in links:
        active = ' aria-current="page"' if href == current else ""
        html.append(f'<a href="{href}"{active}>{_e(label)}</a>')
    return "".join(html)


def _layout(
    spec: WebsiteBuildSpec,
    current: str,
    title: str,
    description: str,
    body: str,
    logo_file: str | None = None,
) -> str:
    brand = _e(spec.brand_name)
    canonical_hint = _e(spec.website_url.rstrip("/"))
    footer_collections = "".join(
        f'<a href="{filename}">{_e(collection.name)}</a>'
        for collection, filename, _ in _collection_entries(spec)
    )
    mark = _brand_mark(spec.brand_name)
    brand_visual = (
        f'<img class="brand-logo" src="{_e(logo_file)}" alt="">'
        if logo_file
        else f'<span class="brand-mark" aria-hidden="true">{mark}</span>'
    )
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
  <link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="assets/styles.css">
  <script defer src="assets/app.js"></script>
</head>
<body data-page="{_e(current)}">
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="site-header">
    <a class="brand" href="index.html" aria-label="{brand} home">
      {brand_visual}
      <span class="brand-name">{brand}</span>
    </a>
    <button class="menu-button" type="button" aria-expanded="false" aria-controls="site-nav">
      <span></span><span></span><span></span><span class="sr-only">Menu</span>
    </button>
    <nav id="site-nav" class="site-nav" aria-label="Main navigation">
      {_nav(spec, current)}
      <a class="nav-cta" href="contact.html">Get pricing</a>
    </nav>
  </header>

  <main id="main">{body}</main>

  <footer class="site-footer">
    <div>
      <a class="brand footer-brand" href="index.html">
        {brand_visual}
        <span class="brand-name">{brand}</span>
      </a>
      <p class="footer-note">{_e(spec.positioning)}</p>
    </div>
    <div class="footer-links">
      {footer_collections}
      <a href="faq.html">FAQ</a>
      <a href="privacy.html">Privacy</a>
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


def _home(spec: WebsiteBuildSpec, hero_images: list[str] | None = None) -> str:
    trust = "".join(
        f'<div class="trust-item"><span>{i:02d}</span><p>{_e(point)}</p></div>'
        for i, point in enumerate(spec.trust_points[:4], 1)
    )
    entries = _collection_entries(spec)
    first, second = entries[0], entries[1]
    hero_images = hero_images or []
    hero_style = ""
    if hero_images:
        hero_style = (
            ' style="background-image:linear-gradient(135deg,rgba(17,16,14,.10),rgba(17,16,14,.50)),'
            f'url(&quot;{_e(hero_images[0])}&quot;);background-size:cover;background-position:center"'
        )
    secondary_hero = "".join(
        f'<div class="hero-mini" style="background-image:url(&quot;{_e(src)}&quot;)"></div>'
        for src in hero_images[1:4]
    )
    return f"""
<section class="hero">
  <div class="hero-copy reveal">
    <p class="eyebrow">{_e(spec.hero_eyebrow)}</p>
    <h1>{_e(spec.hero_heading)}</h1>
    <p class="lede">{_e(spec.hero_subheading)}</p>
    <div class="button-row">
      <a class="button button-primary" href="contact.html">Get pricing</a>
      <a class="button button-ghost" href="#collections">Explore</a>
    </div>
  </div>
  <div class="hero-art reveal"{hero_style} aria-label="{_e(spec.brand_name)} feature visual">
    <div class="orb orb-fire"></div>
    <div class="orb orb-ice"></div>
    <div class="glass-card">
      <span>{_e(first[0].eyebrow)}</span>
      <strong>{_e(first[0].name)}</strong>
      <hr>
      <span>{_e(second[0].eyebrow)}</span>
      <strong>{_e(second[0].name)}</strong>
    </div>
    {f'<div class="hero-mini-grid">{secondary_hero}</div>' if secondary_hero else ''}
  </div>
</section>

<section class="trust-strip" aria-label="Why choose us">{trust}</section>

<section id="collections" class="section">
  <div class="section-heading reveal">
    <p class="eyebrow">Explore</p>
    <h2>Two clear paths into the { _e(spec.brand_name) } experience.</h2>
  </div>
  <div class="collection-grid">
    <a class="collection collection-fire reveal" href="{first[1]}">
      <span class="eyebrow">{_e(first[0].eyebrow)}</span>
      <h3>{_e(first[0].name)}</h3>
      <p>{_e(first[0].intro)}</p>
      <span class="text-link">Explore {_e(first[0].name)} →</span>
    </a>
    <a class="collection collection-ice reveal" href="{second[1]}">
      <span class="eyebrow">{_e(second[0].eyebrow)}</span>
      <h3>{_e(second[0].name)}</h3>
      <p>{_e(second[0].intro)}</p>
      <span class="text-link">Explore {_e(second[0].name)} →</span>
    </a>
  </div>
</section>

<section class="statement">
  <p class="eyebrow">Designed around the customer</p>
  <blockquote>{_e(spec.positioning)}</blockquote>
  <a class="button button-primary" href="contact.html">Start a conversation</a>
</section>
"""


def _collection_page(
    collection: CollectionSpec,
    tone: str,
    product_images: list[str] | None = None,
    image_offset: int = 0,
) -> str:
    product_images = product_images or []
    return f"""
<section class="page-hero page-hero-{tone}">
  <p class="eyebrow">{_e(collection.eyebrow)}</p>
  <h1>{_e(collection.name)}</h1>
  <p class="lede">{_e(collection.intro)}</p>
  <a class="button button-primary" href="contact.html">Request pricing</a>
</section>
<section class="section">
  <div class="section-heading">
    <p class="eyebrow">Collection</p>
    <h2>Explore the options and find the right fit.</h2>
  </div>
  <div class="product-grid">{_product_cards(collection.items, product_images, image_offset)}</div>
</section>
<section class="cta-band">
  <div><p class="eyebrow">Need help choosing?</p><h2>Tell us what you need, your location and your preferred timeline.</h2></div>
  <a class="button button-light" href="contact.html">Start an enquiry</a>
</section>
"""


def _about(spec: WebsiteBuildSpec, about_images: list[str] | None = None) -> str:
    trust = "".join(f"<li>{_e(x)}</li>" for x in spec.trust_points)
    about_images = about_images or []
    image_block = ""
    if about_images:
        tiles = "".join(
            f'<div class="about-photo reveal" style="background-image:url(&quot;{_e(src)}&quot;)" '
            f'aria-label="{_e(spec.brand_name)} image"></div>'
            for src in about_images[:4]
        )
        image_block = f'<div class="about-gallery">{tiles}</div>'
    return f"""
<section class="page-hero">
  <p class="eyebrow">About</p>
  <h1>{_e(spec.about_heading)}</h1>
  <p class="lede">{_e(spec.about_body)}</p>
</section>
<section class="section about-grid">
  <div class="reveal">
    <p class="eyebrow">Our approach</p>
    <h2>A premium customer experience should be clear from the first question to the final handoff.</h2>
    {image_block}
  </div>
  <div class="prose reveal">
    <p>{_e(spec.positioning)}</p>
    <ul class="feature-list">{trust}</ul>
  </div>
</section>
<section class="cta-band">
  <div><p class="eyebrow">Planning a project?</p><h2>Share what you need and we’ll help narrow the options.</h2></div>
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
  <p class="lede">A concise guide to products, services, delivery, customisation and the quotation process.</p>
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
    options = "".join(
        f"<option>{_e(collection.name)}</option>" for collection in spec.collections[:2]
    )
    combined = " + ".join(collection.name for collection in spec.collections[:2])
    return f"""
<section class="page-hero">
  <p class="eyebrow">Get pricing</p>
  <h1>Tell us what you’re planning.</h1>
  <p class="lede">Share what you need, your location and your timing. This staging form works locally and records the enquiry in Darwin’s project database.</p>
</section>
<section class="section contact-grid">
  <div class="contact-copy reveal">
    <p class="eyebrow">Project enquiry</p>
    <h2>Start with the essentials.</h2>
    <p>We’ll use your details to prepare the right conversation. No fake urgency, no automatic purchase and no hidden checkout.</p>
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
    <label>Interest
      <select name="interest" required>
        <option value="">Choose one</option>
        {options}
        <option>{_e(combined)}</option>
        <option>Commercial / bespoke project</option>
      </select>
    </label>
    <label>Project notes<textarea name="message" rows="6" required maxlength="2000" placeholder="What you need, location and desired timeline"></textarea></label>
    <label class="honeypot" aria-hidden="true">Website<input name="company_website" tabindex="-1" autocomplete="off"></label>
    <label class="consent"><input type="checkbox" name="consent" required> <span>I understand these details will be used to respond to my enquiry and have read the <a href="privacy.html">staging privacy notice</a>.</span></label>
    <button class="button button-primary" type="submit">Send enquiry</button>
    <p id="form-status" class="form-status" role="status" aria-live="polite"></p>
  </form>
</section>
"""


def _privacy(spec: WebsiteBuildSpec) -> str:
    return f"""
<section class="page-hero">
  <p class="eyebrow">Privacy</p>
  <h1>Staging privacy notice.</h1>
  <p class="lede">This preview is a pre-launch customer staging environment prepared for {_e(spec.brand_name)}.</p>
</section>
<section class="section two-col">
  <div>
    <p class="eyebrow">What this preview records</p>
    <h2>Only the information submitted through the enquiry form.</h2>
  </div>
  <div class="prose">
    <p>The staging form may record the name, email address, selected interest and project message that a tester submits. The local Darwin preview stores those details in its project database so the customer can verify that the form works.</p>
    <p>No advertising analytics, behavioural tracking pixels or payment checkout are installed by the staging renderer.</p>
    <p>Before public launch, the customer must review and approve the final privacy wording, data-controller contact details, retention period, cookie requirements and any third-party processors used in production.</p>
    <p>This staging notice is operational transparency, not legal advice.</p>
  </div>
</section>
"""


def _not_found(spec: WebsiteBuildSpec) -> str:
    return f"""
<section class="page-hero">
  <p class="eyebrow">404</p>
  <h1>That page isn’t here.</h1>
  <p class="lede">The link may be old or the page may have moved. Use the navigation or return to the {_e(spec.brand_name)} homepage.</p>
  <div class="button-row">
    <a class="button button-primary" href="index.html">Back to home</a>
    <a class="button button-ghost" href="contact.html">Contact us</a>
  </div>
</section>
"""


def _theme_css(spec: WebsiteBuildSpec) -> str:
    heading_fonts = {
        "editorial": 'Georgia, "Times New Roman", serif',
        "modern": 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        "minimal": '"Segoe UI", Inter, ui-sans-serif, system-ui, sans-serif',
    }
    heading_font = heading_fonts.get(spec.design_system.heading_style, heading_fonts["editorial"])
    return (
        "\n:root{"
        f"--fire:{spec.design_system.primary_hex};"
        f"--ice:{spec.design_system.secondary_hex};"
        f"--accent:{spec.design_system.accent_hex};"
        f"--heading-font:{heading_font};"
        "}\n"
    )


STYLES = r"""
:root{
  --ink:#171512;--paper:#f4f0e8;--cream:#ebe4d8;--line:rgba(23,21,18,.14);
  --fire:#9e3d22;--ice:#366575;--accent:#c79a63;--dark:#11100e;--white:#fff;--muted:#6e6a62;--heading-font:Georgia,"Times New Roman",serif;
  --radius:22px;--shadow:0 28px 70px rgba(17,16,14,.12);
}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}
a{color:inherit;text-decoration:none}img{max-width:100%;display:block}button,input,select,textarea{font:inherit}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.skip-link{position:fixed;left:16px;top:-100px;z-index:50;background:#fff;padding:10px 14px;border-radius:8px}.skip-link:focus{top:16px}
.site-header{height:82px;padding:0 clamp(20px,5vw,72px);display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:rgba(244,240,232,.88);backdrop-filter:blur(18px);position:sticky;top:0;z-index:20}
.brand{display:flex;align-items:center;gap:12px;font-weight:650;letter-spacing:.04em}.brand-mark{font-family:Georgia,serif;font-size:22px}.brand-mark span{color:var(--fire)}.brand-logo{display:block;max-width:150px;max-height:42px;object-fit:contain}.brand-name{white-space:nowrap}
.site-nav{display:flex;align-items:center;gap:28px;font-size:13px}.site-nav a{opacity:.75}.site-nav a:hover,.site-nav a[aria-current="page"]{opacity:1}.nav-cta{border:1px solid var(--ink);border-radius:999px;padding:10px 16px;opacity:1!important}
.menu-button{display:none;border:0;background:none;padding:8px}.menu-button span:not(.sr-only){display:block;width:24px;height:1px;background:var(--ink);margin:5px}
.hero{min-height:680px;display:grid;grid-template-columns:1.05fr .95fr;align-items:center;gap:clamp(34px,5vw,76px);padding:clamp(64px,7vw,96px) clamp(20px,6vw,92px)}
.hero-copy{max-width:760px}.eyebrow{text-transform:uppercase;letter-spacing:.18em;font-size:11px;font-weight:750;margin:0 0 18px;color:var(--muted)}
h1,h2,h3,blockquote{font-family:var(--heading-font);font-weight:400;letter-spacing:-.035em;margin-top:0}h1{font-size:clamp(48px,6vw,88px);line-height:.96;margin-bottom:24px}h2{font-size:clamp(34px,4.2vw,58px);line-height:1.04}h3{font-size:32px;line-height:1.05}.lede{font-size:clamp(18px,2vw,24px);max-width:680px;color:#565149}
.button-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:34px}.button{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;padding:14px 22px;font-size:13px;font-weight:700;transition:.2s transform,.2s background}.button:hover{transform:translateY(-2px)}.button-primary{background:var(--ink);color:#fff}.button-ghost{border:1px solid var(--line)}.button-light{background:#fff;color:var(--dark)}
.hero-art{position:relative;min-height:500px;border-radius:36px;background:#171512;overflow:hidden;box-shadow:var(--shadow)}.hero-mini-grid{position:absolute;left:22px;right:22px;top:22px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;z-index:3}.hero-mini{height:92px;border-radius:14px;background-size:cover;background-position:center;border:1px solid rgba(255,255,255,.25);box-shadow:0 10px 24px rgba(0,0,0,.22)}.orb{position:absolute;border-radius:50%;filter:blur(3px)}.orb-fire{width:440px;height:440px;background:radial-gradient(circle at 35% 35%,var(--accent) 0,var(--fire) 48%,transparent 72%);left:-90px;top:-40px}.orb-ice{width:480px;height:480px;background:radial-gradient(circle at 50% 40%,var(--accent) 0,var(--ice) 46%,transparent 72%);right:-120px;bottom:-110px}.glass-card{position:absolute;inset:auto 9% 9% 9%;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);backdrop-filter:blur(20px);color:#fff;padding:28px;border-radius:24px;display:grid;grid-template-columns:90px 1fr;gap:10px 20px}.glass-card hr{grid-column:1/-1;width:100%;border:0;border-top:1px solid rgba(255,255,255,.15)}.glass-card span{font-size:10px;letter-spacing:.2em}.glass-card strong{font-family:var(--heading-font);font-size:24px;font-weight:400}
.trust-strip{display:grid;grid-template-columns:repeat(4,1fr);border-block:1px solid var(--line)}.trust-item{padding:30px clamp(20px,3vw,44px);border-right:1px solid var(--line);display:flex;gap:18px}.trust-item:last-child{border-right:0}.trust-item span{font-size:10px;color:var(--muted)}.trust-item p{margin:0;font-size:13px}
.section{padding:clamp(64px,8vw,112px) clamp(20px,6vw,92px)}.section-heading{max-width:900px;margin-bottom:42px}.collection-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.collection{min-height:460px;padding:40px;border-radius:var(--radius);display:flex;flex-direction:column;justify-content:flex-end;color:#fff;overflow:hidden;position:relative}.collection:before{content:"";position:absolute;inset:0;opacity:.85}.collection>*{position:relative;z-index:1}.collection h3{font-size:clamp(42px,5vw,72px);max-width:600px;margin-bottom:18px}.collection p{max-width:600px}.collection-fire{background:radial-gradient(circle at 70% 5%,var(--accent),var(--fire) 58%,#171512)}.collection-ice{background:radial-gradient(circle at 70% 5%,var(--accent),var(--ice) 58%,#111a1e)}.collection .eyebrow{color:rgba(255,255,255,.68)}.text-link{font-size:13px;font-weight:750;margin-top:20px}
.statement{padding:clamp(80px,10vw,132px) clamp(20px,8vw,120px);background:var(--dark);color:#fff}.statement .eyebrow{color:#a8a198}.statement blockquote{font-size:clamp(42px,6vw,86px);line-height:1.03;max-width:1200px;margin:0 0 42px}
.page-hero{padding:clamp(76px,9vw,120px) clamp(20px,7vw,108px) clamp(54px,7vw,82px)}.page-hero h1{max-width:1050px}.page-hero-fire{background:linear-gradient(145deg,#f4f0e8 45%,color-mix(in srgb,var(--fire),white 72%))}.page-hero-ice{background:linear-gradient(145deg,#f4f0e8 45%,color-mix(in srgb,var(--ice),white 72%))}
.product-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}.product-card{background:#fff;border-radius:var(--radius);overflow:hidden;box-shadow:0 10px 30px rgba(17,16,14,.05)}.product-visual{height:280px;padding:28px;display:flex;align-items:flex-end;background:linear-gradient(135deg,#28241f,var(--fire) 48%,var(--ice));color:#fff}.product-photo{background-size:cover;background-position:center}.product-visual span{font-size:10px;text-transform:uppercase;letter-spacing:.2em}.product-copy{padding:34px}.product-copy p{color:#5f5a52}.detail-list{padding-left:18px;color:#4f4a43}.detail-list li{margin:7px 0}.product-footer{border-top:1px solid var(--line);margin-top:28px;padding-top:20px;display:flex;justify-content:space-between;gap:20px;font-size:13px}
.cta-band{margin:0 clamp(20px,4vw,60px) clamp(20px,4vw,60px);background:var(--dark);color:#fff;border-radius:32px;padding:clamp(42px,6vw,76px);display:flex;align-items:end;justify-content:space-between;gap:30px}.cta-band h2{max-width:900px;margin-bottom:0}.cta-band .eyebrow{color:#aaa49b}
.two-col,.about-grid{display:grid;grid-template-columns:.9fr 1.1fr;gap:clamp(36px,7vw,100px)}.about-gallery{display:grid;grid-template-columns:1.25fr .75fr;gap:10px;margin-top:34px}.about-photo{min-height:220px;border-radius:22px;background-size:cover;background-position:center;box-shadow:var(--shadow)}.about-photo:first-child{grid-row:span 2;min-height:450px}.prose{font-size:19px;color:#504b44}.feature-list{list-style:none;padding:0;margin-top:36px;border-top:1px solid var(--line)}.feature-list li{padding:16px 0;border-bottom:1px solid var(--line)}
.faq-wrap{max-width:1050px;margin:auto}.faq-item{border-top:1px solid var(--line)}.faq-item:last-child{border-bottom:1px solid var(--line)}.faq-item summary{cursor:pointer;list-style:none;padding:26px 0;font-family:var(--heading-font);font-size:25px}.faq-item summary::-webkit-details-marker{display:none}.faq-item summary:after{content:"+";float:right;font-family:Inter,sans-serif}.faq-item[open] summary:after{content:"−"}.faq-item div{padding:0 0 26px;max-width:800px;color:#5d5850}
.contact-grid{display:grid;grid-template-columns:.85fr 1.15fr;gap:8vw;align-items:start}.contact-copy{position:sticky;top:130px}.contact-details{margin-top:36px}.contact-details a{text-decoration:underline}.quote-form{background:#fff;padding:clamp(28px,4vw,52px);border-radius:var(--radius);box-shadow:var(--shadow)}.quote-form label{display:grid;gap:8px;font-size:12px;font-weight:700;margin-bottom:20px}.quote-form input,.quote-form select,.quote-form textarea{width:100%;border:1px solid #d6d0c6;border-radius:12px;padding:14px 15px;background:#fbfaf7;color:var(--ink)}.quote-form input:focus,.quote-form select:focus,.quote-form textarea:focus{outline:2px solid #6f8991;outline-offset:2px}.field-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}.honeypot{position:absolute!important;left:-9999px!important;width:1px!important;height:1px!important;overflow:hidden!important}.consent{display:flex!important;grid-template-columns:auto 1fr!important;align-items:flex-start}.consent input{width:auto;margin-top:4px}.form-status{min-height:24px;font-size:13px}.form-status.success{color:#17653a}.form-status.error{color:#a12b2b}
.site-footer{background:#0f0e0c;color:#fff;padding:64px clamp(20px,6vw,90px);display:grid;grid-template-columns:1.3fr .6fr 1fr;gap:50px}.footer-brand{margin-bottom:20px}.footer-note{color:#aaa49b;max-width:480px;font-size:12px}.footer-links{display:grid;gap:10px;font-size:13px}.site-footer .eyebrow{color:#aaa49b}
.reveal{animation:fadeUp .7s ease both}@keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
@media(max-width:900px){
  .site-header{height:70px}.menu-button{display:block}.site-nav{display:none;position:absolute;top:70px;left:0;right:0;background:var(--paper);padding:24px;box-shadow:0 18px 40px rgba(0,0,0,.08);flex-direction:column;align-items:flex-start}.site-nav.open{display:flex}
  .hero{grid-template-columns:1fr;padding-top:70px}.hero-art{min-height:440px}.trust-strip{grid-template-columns:1fr 1fr}.trust-item:nth-child(2){border-right:0}.trust-item{border-bottom:1px solid var(--line)}
  .collection-grid,.product-grid,.two-col,.about-grid,.contact-grid{grid-template-columns:1fr}.collection{min-height:400px}.contact-copy{position:static}.site-footer{grid-template-columns:1fr}.cta-band{align-items:flex-start;flex-direction:column}
}
@media(max-width:560px){h1{font-size:44px}.hero{min-height:auto;padding-top:48px}.hero-art{min-height:340px}.hero-mini-grid{grid-template-columns:repeat(2,1fr)}.hero-mini{height:72px}.about-gallery{grid-template-columns:1fr 1fr}.about-photo:first-child{grid-row:auto;grid-column:1/-1;min-height:280px}.glass-card{grid-template-columns:60px 1fr;padding:20px}.trust-strip{grid-template-columns:1fr}.trust-item{border-right:0}.collection{padding:30px;min-height:400px}.product-grid{grid-template-columns:1fr}.field-row{grid-template-columns:1fr}.product-footer{flex-direction:column}}
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


def render_site(
    spec: WebsiteBuildSpec,
    output_dir: Path,
    image_files: list[str] | None = None,
    logo_file: str | None = None,
    about_image: str | None = None,
    hero_image: str | None = None,
    product_images: list[str] | None = None,
    hero_images: list[str] | None = None,
    about_images: list[str] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = output_dir / "assets"
    assets.mkdir(exist_ok=True)
    image_files = image_files or []
    hero_images = list(hero_images or [])
    about_images = list(about_images or [])
    if hero_image and hero_image not in hero_images:
        hero_images.insert(0, hero_image)
    if about_image and about_image not in about_images:
        about_images.insert(0, about_image)
    if not hero_images and image_files:
        hero_images = [image_files[0]]
    if product_images is None:
        product_images = image_files[1:] if len(image_files) > 1 else []
    product_images = product_images or []

    entries = _collection_entries(spec)
    pages = {
        "index.html": (
            f"{spec.brand_name}",
            spec.hero_subheading,
            _home(spec, hero_images),
        ),
        "about.html": (
            "About",
            spec.about_body,
            _about(spec, about_images),
        ),
        "faq.html": (
            "Frequently asked questions",
            "Answers about products, services, delivery, customisation and quotations.",
            _faq(spec),
        ),
        "contact.html": (
            "Get pricing",
            f"Request pricing and discuss your project with {spec.brand_name}.",
            _contact(spec),
        ),
        "privacy.html": (
            "Privacy",
            "Staging privacy and data-handling information.",
            _privacy(spec),
        ),
        "404.html": (
            "Page not found",
            "The requested page could not be found.",
            _not_found(spec),
        ),
    }

    for collection, filename, index in entries:
        pages[filename] = (
            collection.name,
            collection.intro,
            _collection_page(
                collection,
                "fire" if index == 1 else "ice",
                product_images,
                0 if index == 1 else len(spec.collections[0].items),
            ),
        )

    for filename, (title, description, body) in pages.items():
        (output_dir / filename).write_text(
            _layout(spec, filename, title, description, body, logo_file=logo_file),
            encoding="utf-8",
        )

    favicon = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="16" fill="#171512"/>
<text x="32" y="39" text-anchor="middle" font-family="Georgia,serif" font-size="25" fill="#f4f0e8">{escape(spec.brand_name[:1].upper())}</text>
</svg>"""
    (assets / "styles.css").write_text(STYLES + _theme_css(spec), encoding="utf-8")
    (assets / "app.js").write_text(APP_JS, encoding="utf-8")
    (assets / "favicon.svg").write_text(favicon, encoding="utf-8")
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
                "pages": list(pages.keys()),
                "collections": [c.name for c, _, _ in entries],
                "design_system": spec.design_system.model_dump(),
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
    expected = list(BASE_REQUIRED_PAGES)
    build_file = output_dir / "build.json"
    if build_file.exists():
        try:
            payload = json.loads(build_file.read_text(encoding="utf-8"))
            expected = list(payload.get("pages") or expected)
        except Exception:
            errors.append("build.json is not valid JSON")

    for name in expected:
        path = output_dir / name
        if not path.exists():
            errors.append(f"Missing page: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        if "<title>" not in text or "<main" not in text:
            errors.append(f"Malformed document structure: {name}")
        if 'name="robots" content="noindex,nofollow"' not in text:
            errors.append(f"Staging noindex missing: {name}")

    for name in [
        "assets/styles.css",
        "assets/app.js",
        "assets/favicon.svg",
        "build.json",
        "robots.txt",
    ]:
        if not (output_dir / name).exists():
            errors.append(f"Missing asset: {name}")

    contact = output_dir / "contact.html"
    if contact.exists():
        text = contact.read_text(encoding="utf-8")
        if 'id="quote-form"' not in text or "/api/quote" not in APP_JS:
            errors.append("Functional quote form wiring missing")

    generated = {p.name for p in output_dir.glob("*.html")}
    link_pattern = re.compile(r'href="([^"]+\.html)(?:#[^"]*)?"')
    for page in output_dir.glob("*.html"):
        for href in link_pattern.findall(page.read_text(encoding="utf-8")):
            target = Path(urlparse(href).path).name
            if target and target not in generated:
                errors.append(f"Broken internal link in {page.name}: {href}")

    return sorted(set(errors))
