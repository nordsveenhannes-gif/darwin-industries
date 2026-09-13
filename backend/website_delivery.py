from __future__ import annotations

import os
import re

import resend


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
- Website build: \${build_price:,.0f} one-time
- Hosting & care: \${monthly_price:,.0f}/month

The monthly plan includes hosting, SSL, backups, uptime monitoring, and one small content/update request per month (up to roughly 30 minutes of work). Larger changes are quoted before we start them, so there are no surprise fees.

Please review the concept and reply with one consolidated round of feedback, or tell us if you’d like to move forward.

We do not take ownership of your domain, and you can cancel the monthly care plan and take your website files with you.

Best,
Mercury
Darwin Industries
""".format(
        business_name=business_name,
        preview_line=preview_line,
        build_price=build_price_usd,
        monthly_price=monthly_price_usd,
    )

    resend.api_key = api_key
    response = resend.Emails.send(
        {
            "from": from_email,
            "to": [recipient],
            "subject": subject,
            "text": body,
            "reply_to": reply_to,
            "tags": [
                {"name": "source", "value": "darwin_website_studio"},
                {"name": "stage", "value": "staging_ready"},
            ],
        }
    )
    return _response_id(response)
