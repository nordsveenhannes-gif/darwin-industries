from __future__ import annotations

import html
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from backend.storage import connect, init_db, now_iso


INITIAL_QUESTIONS = [
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


def _page(project_id: int, business_name: str, questions: list[dict], heading: str) -> bytes:
    fields = []
    for q in questions:
        key = html.escape(q["key"], quote=True)
        question = html.escape(q["question"])
        why = html.escape(q.get("why", ""))
        placeholder = html.escape(q.get("placeholder", ""), quote=True)
        fields.append(
            f"""
            <section class="question">
              <label for="{key}">{question}</label>
              <p>{why}</p>
              <textarea id="{key}" name="{key}" rows="4" required
                placeholder="{placeholder}"></textarea>
            </section>
            """
        )

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Website project questionnaire</title>
<style>
:root{{--ink:#171512;--paper:#f4f0e8;--card:#fff;--muted:#6a655d;--line:#d9d1c5;--accent:#1f4c5b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{width:min(860px,calc(100% - 32px));margin:56px auto}}.eyebrow{{text-transform:uppercase;letter-spacing:.18em;font-size:11px;font-weight:800;color:var(--muted)}}
h1{{font:400 clamp(40px,7vw,72px)/.98 Georgia,serif;letter-spacing:-.04em;margin:10px 0 18px}}.intro{{font-size:19px;color:#514b43;max-width:720px}}
.notice{{background:#171512;color:#fff;border-radius:18px;padding:18px 20px;margin:30px 0;font-size:13px}}form{{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:clamp(22px,5vw,48px);box-shadow:0 24px 70px rgba(23,21,18,.08)}}
.question{{padding:0 0 30px;margin-bottom:30px;border-bottom:1px solid #eee8df}}.question:last-of-type{{border-bottom:0}}label{{display:block;font:400 25px/1.15 Georgia,serif;margin-bottom:8px}}
.question p{{margin:0 0 14px;color:var(--muted);font-size:13px}}textarea{{width:100%;resize:vertical;border:1px solid #cfc7bb;background:#fbfaf7;border-radius:12px;padding:14px 15px;color:var(--ink);font:inherit}}
textarea:focus{{outline:2px solid #6e98a4;outline-offset:2px}}button{{border:0;border-radius:999px;background:var(--ink);color:white;padding:14px 24px;font-weight:800;cursor:pointer}}
.small{{font-size:12px;color:var(--muted);margin-top:14px}}
</style>
</head>
<body>
<main>
<p class="eyebrow">Darwin Industries · Client onboarding</p>
<h1>{html.escape(heading)}</h1>
<p class="intro">Project: <strong>{html.escape(business_name)}</strong>. These are the same kinds of questions a web agency asks before committing design and content decisions.</p>
<div class="notice">Do not enter passwords, API keys, card details or domain credentials here. Those are handled separately through secure owner-controlled access when a real project reaches launch.</div>
<form method="post" action="/submit">
{''.join(fields)}
<button type="submit">Send answers and continue the build</button>
<p class="small">Darwin will save these answers to the project record, close this questionnaire and continue the staging build automatically.</p>
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
    questions = questions or INITIAL_QUESTIONS
    _seed_questions(project_id, questions)
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_response(404)
                self.end_headers()
                return
            payload = _page(project_id, business_name, questions, heading)
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
            if length <= 0 or length > 100000:
                self.send_response(400)
                self.end_headers()
                return
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            missing = []
            answers = {}
            for q in questions:
                answer = (form.get(q["key"], [""])[0] or "").strip()
                if not answer:
                    missing.append(q["question"])
                answers[q["key"]] = answer
            if missing:
                payload = (
                    "<h1>Please answer every required question.</h1>"
                    "<p>Use your browser Back button and complete the missing fields.</p>"
                ).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

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
            conn.execute(
                "UPDATE website_projects SET status='CLIENT_BRIEF_COMPLETE',updated_at=? WHERE id=?",
                (now_iso(), project_id),
            )
            conn.commit()
            conn.close()

            payload = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{font-family:system-ui;background:#f4f0e8;color:#171512;display:grid;place-items:center;min-height:90vh}}
div{{max-width:620px;background:white;padding:42px;border-radius:24px}}h1{{font-family:Georgia,serif;font-size:42px}}
</style></head><body><div><h1>Thanks — Darwin has the brief.</h1>
<p>The agents are continuing the build now. You can close this tab and watch Mission Control.</p></div></body></html>""".encode("utf-8")
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
    print("Darwin is waiting for the customer's answers before it commits the staging design.\n")

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
