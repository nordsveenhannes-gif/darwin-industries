from __future__ import annotations

import os
import re

import resend

from backend.branding import CLIENT_NAME, CLIENT_TAGLINE


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _response_id(response) -> str:
    if isinstance(response, dict):
        return str(response.get("id") or "")
    return str(getattr(response, "id", "") or "")


def send_website_ready_email(
    *,
    to_email: str,
    business_name: str,
    build_price_usd: float,
    monthly_price_usd: float,
    preview_url: str | None = None,
) -> str:
    recipient = (to_email or "").strip()
    if not EMAIL_RE.match(recipient):
        raise RuntimeError("A valid client project email is required for website delivery.")

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("DARWIN_EMAIL_FROM", "").strip()
    reply_to = os.getenv("DARWIN_EMAIL_REPLY_TO", "").strip()
    if not api_key or not from_email or not reply_to:
        raise RuntimeError(
            "Website delivery email requires RESEND_API_KEY, DARWIN_EMAIL_FROM, "
            "and DARWIN_EMAIL_REPLY_TO in .env."
        )

    preview_line = (
        "\nPrivate staging preview: {0}\n".format(preview_url)
        if preview_url
        else "\nThe staging concept is complete. We’ll provide the private review link separately once the preview is published.\n"
    )

    subject = "{0} — your website concept is ready".format(business_name)
    body = """Hi,

Thanks for the brief. We’ve finished the first website concept for {business_name}.
{preview_line}
Our proposal:
- Website build: ${build_price:,.0f} one-time
- Hosting & care: ${monthly_price:,.0f}/month

The monthly plan includes hosting, SSL, backups, uptime monitoring, and one small content/update request per month (up to roughly 30 minutes of work). Larger changes are quoted before we start them, so there are no surprise fees.

Please review the concept and reply with one consolidated round of feedback, or tell us if you’d like to move forward.

We do not take ownership of your domain, and you can cancel the monthly care plan and take your website files with you.

Best,
Mercury
Shenanigan Systems
""".format(
        business_name=business_name,
        preview_line=preview_line,
        build_price=build_price_usd,
        monthly_price=monthly_price_usd,
    )

    preview_button = (
        '<p><a href="' + preview_url + '" style="display:inline-block;padding:12px 18px;'
        'border-radius:999px;background:#ff6a00;color:#0a0810;text-decoration:none;'
        'font-weight:900">Review staging concept</a></p>'
        if preview_url
        else ""
    )
    html = f"""<!doctype html>
<html><body style="margin:0;background:#0a0810;color:#f7f2e8;font-family:Arial,sans-serif">
<div style="max-width:680px;margin:0 auto;padding:36px 24px">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:28px">
    <div style="width:42px;height:42px;border:1px solid #ff6a00;border-radius:12px;display:grid;place-items:center;background:#14101c;font:bold 17px Consolas,monospace">S<span style="color:#b7ff4a">S</span></div>
    <div><div style="font:bold 13px Consolas,monospace;letter-spacing:.16em">{CLIENT_NAME.upper()}</div><div style="color:#9e96aa;font-size:12px">{CLIENT_TAGLINE}</div></div>
  </div>
  <h1 style="font-size:32px;margin:0 0 18px">{business_name} website concept is ready.</h1>
  <p style="color:#c8c0cf;line-height:1.65">Thanks for the brief. We’ve finished the first website concept.</p>
  <div style="background:#14101c;border:1px solid #2a2136;border-radius:16px;padding:20px;margin:24px 0">
    <div style="font-size:22px;font-weight:800">&#36;{build_price_usd:,.0f} one-time</div>
    <div style="color:#b7ff4a;font-weight:800">&#36;{monthly_price_usd:,.0f}/month hosting & care</div>
  </div>
  <p style="color:#c8c0cf;line-height:1.65">The monthly plan includes hosting, SSL, backups, uptime monitoring and one small content/update request per month. Larger changes are quoted first.</p>
  {preview_button}
  <p style="color:#c8c0cf;line-height:1.65">Reply with one consolidated round of feedback, or tell us if you’d like to move forward.</p>
  <p style="color:#7f788a;font-size:12px;margin-top:28px">Your domain stays under your control. If you cancel hosting & care, you can take the website files with you.</p>
</div></body></html>"""

    sender = from_email if "<" in from_email else f"{CLIENT_NAME} <{from_email}>"
    resend.api_key = api_key
    response = resend.Emails.send(
        {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": body,
            "html": html,
            "reply_to": reply_to,
            "tags": [
                {"name": "source", "value": "darwin_website_studio"},
                {"name": "stage", "value": "staging_ready"},
            ],
        }
    )
    return _response_id(response)
