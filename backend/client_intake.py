from __future__ import annotations

import html
import re
import threading
import time
import webbrowser
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from backend.storage import connect, init_db, now_iso
from backend.branding import CLIENT_NAME, client_logo_css, client_logo_html


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
UPLOAD_FIELDS = {
    "logo_files": "logo",
    "hero_files": "hero",
    "product_files": "product",
    "about_files": "about",
}
MAX_UPLOAD_BYTES = 5_000_000
MAX_UPLOAD_FILES = 24
MAX_FORM_BYTES = 100_000_000


INITIAL_QUESTIONS = [
    {
        "key": "client_email",
        "question": "Where should we email the finished proposal and staging review?",
        "why": "Shenanigan Systems uses this only for this website project and project follow-up.",
        "required_for": "STAGING",
        "input_type": "email",
        "placeholder": "you@business.com",
    },
    {
        "key": "primary_goal",
        "question": "What is the main job this website should do?",
        "why": "This determines the page hierarchy and what Darwin optimizes the experience around.",
        "required_for": "STAGING",
        "placeholder": "Example: Generate more serious quotation requests for premium home installations.",
    },
    {
        "key": "target_audience",
        "question": "Who are the most important customers we should design for?",
        "why": "A premium site still needs to speak to a specific buyer rather than everybody.",
        "required_for": "STAGING",
        "placeholder": "Example: High-income homeowners, interior designers, boutique gyms and wellness spaces.",
    },
    {
        "key": "primary_action",
        "question": "What should a visitor ideally do before leaving the site?",
        "why": "Darwin needs one clear primary conversion instead of competing calls to action.",
        "required_for": "STAGING",
        "placeholder": "Example: Request pricing / book a consultation / call / buy online.",
    },
    {
        "key": "brand_direction",
        "question": "How should the new site feel, and what should we keep or avoid from the current brand?",
        "why": "This prevents Darwin from imposing a generic design direction the client never asked for.",
        "required_for": "STAGING",
        "placeholder": "Example: Quiet luxury, architectural, warm/cold contrast. Keep the logo. Avoid flashy gradients and salesy wording.",
    },
    {
        "key": "required_functionality",
        "question": "What functionality is required for this project?",
        "why": "Forms, booking, ecommerce, galleries, CRM connections and other features materially change scope and architecture.",
        "required_for": "STAGING",
        "placeholder": "Example: Quote form only. No checkout. We may add booking later.",
    },
    {
        "key": "commercial_facts",
        "question": "Which existing commercial facts are still current, and what needs correcting?",
        "why": "Pricing, VAT, lead times, shipping, installation and warranties should never be guessed.",
        "required_for": "STAGING",
        "placeholder": "Example: Current product prices are correct; lead time is around 6 weeks; shipping is extra; installation is quoted separately.",
    },
    {
        "key": "staging_asset_permission",
        "question": "May Darwin reuse the logo, copy and images already published on the current site in this private staging preview?",
        "why": "A redesign can look realistic without treating public availability as proof of production licensing rights.",
        "required_for": "STAGING",
        "placeholder": "Answer yes/no and note any images, logos or copy we must not reuse.",
    },
    {
        "key": "approver_and_deadline",
        "question": "Who is the single person who approves feedback, and is there a hard launch date or event?",
        "why": "A clear approver and deadline prevent conflicting revisions and unrealistic delivery expectations.",
        "required_for": "STAGING",
        "placeholder": "Example: I approve all revisions. No hard event, but we would like to launch within 3 weeks.",
    },
]


LAUNCH_QUESTIONS = [
    {
        "key": "launch_legal_identity",
        "question": "Confirm the legal/trading name, business address and any company/VAT details that must appear publicly.",
        "why": "Production legal and commercial pages should use customer-confirmed identity details.",
        "required_for": "LAUNCH",
    },
    {
        "key": "launch_form_destination",
        "question": "Where should production website enquiries go, and what response expectation should the site communicate?",
        "why": "The live form must be routed and tested against a real customer-owned inbox or CRM.",
        "required_for": "LAUNCH",
    },
    {
        "key": "launch_asset_rights",
        "question": "Confirm that the customer owns or licenses every logo, image, font, video and piece of copy that will ship.",
        "why": "Public launch requires production asset rights, not merely staging permission.",
        "required_for": "LAUNCH",
    },
    {
        "key": "launch_privacy_cookies",
        "question": "Provide/approve the privacy notice and identify any analytics, advertising, chat or other non-essential cookies/trackers required.",
        "why": "The production site must accurately disclose data processing and configure consent where required.",
        "required_for": "LAUNCH",
    },
    {
        "key": "launch_seo_migration",
        "question": "Which existing URLs, SEO pages, analytics/Search Console properties and tracking must be preserved during the redesign?",
        "why": "A redesign can damage search visibility if old URLs, redirects, metadata and measurement are ignored.",
        "required_for": "LAUNCH",
    },
    {
        "key": "launch_hosting_domain",
        "question": "Who owns the domain and hosting, and who can grant secure production access when launch is approved?",
        "why": "Darwin should never take ownership of the client's domain or request ordinary-email passwords.",
        "required_for": "LAUNCH",
    },
]


def _seed_questions(project_id: int, questions: list[dict]) -> None:
    conn = connect()
    init_db(conn)
    for q in questions:
        conn.execute(
            """
            INSERT INTO website_client_questions(
                project_id,question_key,question,why_needed,required_for,status,created_at
            )
            VALUES(?,?,?,?,?,'OPEN',?)
            ON CONFLICT(project_id,question_key) DO UPDATE SET
                question=excluded.question,
                why_needed=excluded.why_needed,
                required_for=excluded.required_for
            """,
            (
                project_id,
                q["key"],
                q["question"],
                q.get("why", ""),
                q.get("required_for", "STAGING"),
                now_iso(),
            ),
        )
    conn.commit()
    conn.close()


def seed_launch_questions(project_id: int) -> None:
    _seed_questions(project_id, LAUNCH_QUESTIONS)


def answers_for_project(project_id: int) -> dict[str, str]:
    conn = connect()
    init_db(conn)
    rows = conn.execute(
        """
        SELECT question_key,answer
        FROM website_client_questions
        WHERE project_id=? AND status='ANSWERED'
        ORDER BY id
        """,
        (project_id,),
    ).fetchall()
    conn.close()
    return {row["question_key"]: row["answer"] or "" for row in rows}


def assets_for_project(project_id: int) -> list[dict]:
    conn = connect()
    init_db(conn)
    rows = conn.execute(
        """
        SELECT category,original_name,stored_path,mime_type,size_bytes
        FROM website_client_assets
        WHERE project_id=?
        ORDER BY CASE category
            WHEN 'logo' THEN 1
            WHEN 'hero' THEN 2
            WHEN 'product' THEN 3
            WHEN 'about' THEN 4
            ELSE 9 END, id
        """,
        (project_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _safe_filename(value: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(value).name).strip("-")
    return stem[:100] or "image"


def _save_uploads(project_id: int, uploads: list[tuple[str, str, str, bytes]]) -> int:
    if not uploads:
        return 0

    root = Path("client_uploads") / f"website-{project_id}"
    root.mkdir(parents=True, exist_ok=True)

    conn = connect()
    init_db(conn)
    saved = 0
    for field_name, filename, mime_type, data in uploads[:MAX_UPLOAD_FILES]:
        category = UPLOAD_FIELDS.get(field_name)
        ext = ALLOWED_IMAGE_TYPES.get(mime_type)
        if not category or not ext or not data:
            continue
        if len(data) > MAX_UPLOAD_BYTES:
            continue

        base = Path(_safe_filename(filename)).stem[:70] or category
        stored_name = f"{category}-{saved + 1:02d}-{base}{ext}"
        path = root / stored_name
        suffix = 2
        while path.exists():
            path = root / f"{category}-{saved + 1:02d}-{base}-{suffix}{ext}"
            suffix += 1

        path.write_bytes(data)
        conn.execute(
            """
            INSERT INTO website_client_assets(
                project_id,category,original_name,stored_path,mime_type,size_bytes,created_at
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                project_id,
                category,
                filename[:250],
                str(path),
                mime_type,
                len(data),
                now_iso(),
            ),
        )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def _parse_submission(handler: BaseHTTPRequestHandler, length: int):
    content_type = handler.headers.get("Content-Type", "")
    body = handler.rfile.read(length)

    if content_type.lower().startswith("multipart/form-data"):
        raw = (
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
            + body
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)
        fields: dict[str, str] = {}
        uploads: list[tuple[str, str, str, bytes]] = []
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            field_name = part.get_param("name", header="content-disposition")
            if not field_name:
                continue
            filename = part.get_filename()
            if filename:
                uploads.append(
                    (
                        str(field_name),
                        str(filename),
                        part.get_content_type(),
                        part.get_payload(decode=True) or b"",
                    )
                )
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            fields[str(field_name)] = payload.decode(charset, errors="replace")
        return fields, uploads

    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}, []


def _page(
    project_id: int,
    business_name: str,
    questions: list[dict],
    heading: str,
    existing_answers: dict[str, str] | None = None,
    show_asset_uploads: bool = False,
) -> bytes:
    existing_answers = existing_answers or {}
    fields = []
    for q in questions:
        key = html.escape(q["key"], quote=True)
        question = html.escape(q["question"])
        why = html.escape(q.get("why", ""))
        placeholder = html.escape(q.get("placeholder", ""), quote=True)
        options = q.get("options") or []
        input_type = q.get("input_type")

        if options:
            selected_value = existing_answers.get(q["key"], "")
            option_html = '<option value="">Choose one</option>' + "".join(
                f'<option value="{html.escape(str(opt), quote=True)}"'
                + (' selected' if str(opt) == selected_value else '')
                + f'>{html.escape(str(opt))}</option>'
                for opt in options
            )
            control = f'<select id="{key}" name="{key}" required>{option_html}</select>'
        elif input_type == "email":
            existing = html.escape(existing_answers.get(q["key"], ""), quote=True)
            control = (
                f'<input id="{key}" name="{key}" type="email" value="{existing}" '
                f'placeholder="{placeholder}" autocomplete="email" required>'
            )
        else:
            existing = html.escape(existing_answers.get(q["key"], ""))
            control = (
                f'<textarea id="{key}" name="{key}" rows="4" required '
                f'placeholder="{placeholder}">{existing}</textarea>'
            )

        fields.append(
            f"""
            <section class="question">
              <label for="{key}">{question}</label>
              <p>{why}</p>
              {control}
            </section>
            """
        )

    assets_html = ""
    if show_asset_uploads:
        existing_assets = assets_for_project(project_id)
        current = ""
        if existing_assets:
            current = (
                f'<p class="small good">Already uploaded: {len(existing_assets)} image(s). '
                "You can add more below.</p>"
            )
        assets_html = f"""
        <section class="uploads">
          <p class="eyebrow">Your images</p>
          <h2>Upload the pictures you actually want us to use.</h2>
          <p>Optional, but recommended. Categorising them helps our design system place the right image in the right part of the site instead of guessing.</p>
          {current}
          <div class="upload-grid">
            <label class="upload-card">Logo / brand mark
              <span>PNG, JPG or WebP</span>
              <input type="file" name="logo_files" accept="image/png,image/jpeg,image/webp">
            </label>
            <label class="upload-card">Hero / homepage
              <span>Select several wide/lifestyle images — we can use up to 4 in the hero area</span>
              <input type="file" name="hero_files" accept="image/png,image/jpeg,image/webp" multiple>
            </label>
            <label class="upload-card">Products / services
              <span>Select several product/service photos — we distribute them across cards</span>
              <input type="file" name="product_files" accept="image/png,image/jpeg,image/webp" multiple>
            </label>
            <label class="upload-card">About / team / location
              <span>Select several team/showroom/location photos — we build an image gallery</span>
              <input type="file" name="about_files" accept="image/png,image/jpeg,image/webp" multiple>
            </label>
          </div>
          <p class="small">You can select multiple files at once for hero, products/services and about. Maximum 5 MB per image, 24 images per brief. We prioritise these over automatically discovered imagery.</p>
        </section>
        """

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Website project questionnaire</title>
<style>
:root{{--ink:#171512;--paper:#f4f0e8;--card:#fff;--muted:#6a655d;--line:#d9d1c5;--accent:#1f4c5b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{width:min(900px,calc(100% - 32px));margin:56px auto}}.eyebrow{{text-transform:uppercase;letter-spacing:.18em;font-size:11px;font-weight:800;color:var(--muted)}}
h1{{font:400 clamp(40px,7vw,72px)/.98 Georgia,serif;letter-spacing:-.04em;margin:10px 0 18px}}h2{{font:400 32px/1.05 Georgia,serif;margin:8px 0 12px}}.intro{{font-size:19px;color:#514b43;max-width:720px}}
.notice{{background:#171512;color:#fff;border-radius:18px;padding:18px 20px;margin:30px 0;font-size:13px}}form{{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:clamp(22px,5vw,48px);box-shadow:0 24px 70px rgba(23,21,18,.08)}}
.question{{padding:0 0 30px;margin-bottom:30px;border-bottom:1px solid #eee8df}}.question:last-of-type{{border-bottom:0}}label{{display:block;font:400 24px/1.15 Georgia,serif;margin-bottom:8px}}
.question p,.uploads>p{{margin:0 0 14px;color:var(--muted);font-size:13px}}textarea,select,input[type=email]{{width:100%;border:1px solid #cfc7bb;background:#fbfaf7;border-radius:12px;padding:14px 15px;color:var(--ink);font:inherit}}
textarea{{resize:vertical}}textarea:focus,select:focus,input:focus{{outline:2px solid #6e98a4;outline-offset:2px}}
.uploads{{margin:10px 0 34px;padding:28px;border-radius:18px;background:#f7f3ec;border:1px solid #e3dbcf}}.upload-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:18px}}
.upload-card{{font:700 14px/1.3 system-ui;padding:16px;background:#fff;border:1px solid #ddd4c8;border-radius:14px;cursor:pointer}}.upload-card span{{display:block;color:var(--muted);font-size:11px;font-weight:500;margin:5px 0 12px}}.upload-card input{{width:100%;font:12px system-ui}}
button{{border:0;border-radius:999px;background:var(--ink);color:white;padding:14px 24px;font-weight:800;cursor:pointer}}.small{{font-size:12px;color:var(--muted);margin-top:14px}}.good{{color:#285e48!important}}
@media(max-width:700px){{.upload-grid{{grid-template-columns:1fr}}}}
{client_logo_css()}
.client-brand{margin-bottom:22px}.client-brand .ss-word{font-size:13px}
</style>
</head>
<body>
<main>
<div class="client-brand">{client_logo_html()}</div>
<p class="eyebrow">{CLIENT_NAME} · Client onboarding</p>
<h1>{html.escape(heading)}</h1>
<p class="intro">Project: <strong>{html.escape(business_name)}</strong>. Your answers become the working brief for the design team.</p>
<div class="notice">Do not enter passwords, API keys, card details or domain credentials here. Those are handled separately through secure owner-controlled access if the project reaches launch.</div>
<form method="post" action="/submit" enctype="multipart/form-data">
{''.join(fields)}
{assets_html}
<button type="submit">Send brief and start the build</button>
<p class="small">After this, our design system starts the work. If the project is deliverable within the agreed scope, the next client-facing message should be the finished proposal/staging review — not another copy of this form.</p>
</form>
</main>
</body></html>"""
    return body.encode("utf-8")


def collect_client_answers(
    project_id: int,
    business_name: str,
    questions: list[dict] | None = None,
    port: int = 8790,
    heading: str = "Before we design, we need your brief.",
    open_browser: bool = True,
) -> dict[str, str]:
    is_initial = questions is None
    questions = questions or INITIAL_QUESTIONS
    _seed_questions(project_id, questions)

    existing_answers = answers_for_project(project_id)
    question_keys = {q["key"] for q in questions}
    already_answered = {
        key: value for key, value in existing_answers.items() if key in question_keys and value.strip()
    }
    if len(already_answered) == len(question_keys):
        return already_answered

    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_response(404)
                self.end_headers()
                return
            payload = _page(
                project_id,
                business_name,
                questions,
                heading,
                existing_answers=answers_for_project(project_id),
                show_asset_uploads=is_initial,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            if self.path != "/submit":
                self.send_response(404)
                self.end_headers()
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_FORM_BYTES:
                self.send_response(400)
                self.end_headers()
                return

            fields, uploads = _parse_submission(self, length)
            missing = []
            answers: dict[str, str] = {}
            for q in questions:
                answer = (fields.get(q["key"]) or "").strip()
                if not answer:
                    missing.append(q["question"])
                if q.get("input_type") == "email" and answer and not EMAIL_RE.match(answer):
                    missing.append("a valid project email address")
                answers[q["key"]] = answer

            if missing:
                payload = (
                    "<h1>Please complete every required field.</h1>"
                    "<p>Use your browser Back button and complete the missing or invalid fields.</p>"
                ).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            saved_assets = _save_uploads(project_id, uploads) if is_initial else 0

            conn = connect()
            init_db(conn)
            for q in questions:
                conn.execute(
                    """
                    UPDATE website_client_questions
                    SET answer=?,status='ANSWERED',answered_at=?
                    WHERE project_id=? AND question_key=?
                    """,
                    (answers[q["key"]], now_iso(), project_id, q["key"]),
                )

            if "client_email" in answers:
                conn.execute(
                    "UPDATE website_projects SET customer_email=?,status='CLIENT_BRIEF_COMPLETE',updated_at=? WHERE id=?",
                    (answers["client_email"], now_iso(), project_id),
                )
            else:
                conn.execute(
                    "UPDATE website_projects SET status='CLIENT_BRIEF_COMPLETE',updated_at=? WHERE id=?",
                    (now_iso(), project_id),
                )
            conn.commit()
            conn.close()

            upload_note = (
                f"<p>We received {saved_assets} client image(s) and will prioritise them in the design.</p>"
                if saved_assets
                else ""
            )
            payload = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{font-family:system-ui;background:#f4f0e8;color:#171512;display:grid;place-items:center;min-height:90vh}}
div{{max-width:620px;background:white;padding:42px;border-radius:24px}}h1{{font-family:Georgia,serif;font-size:42px}}p{{line-height:1.6;color:#514b43}}
</style></head><body><div><h1>Thanks — we have your brief.</h1>
<p>Our design team is starting the website concept now.</p>
{upload_note}
<p>We’ll email the finished proposal and review details to the address you supplied when the staging concept is ready.</p>
</div></body></html>""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            done.set()

        def log_message(self, format, *args):
            return

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    actual_port = int(server.server_port)
    print("\n=== CLIENT WEBSITE QUESTIONNAIRE ===")
    print(f"Open: http://127.0.0.1:{actual_port}")
    print("Shenanigan Systems is waiting for the customer's brief before starting the design.\n")

    if open_browser:
        threading.Timer(
            0.7,
            lambda: webbrowser.open(f"http://127.0.0.1:{actual_port}"),
        ).start()

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        while not done.wait(0.25):
            pass
        time.sleep(0.5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return answers_for_project(project_id)
