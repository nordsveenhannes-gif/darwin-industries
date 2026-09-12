from __future__ import annotations

import shutil
from pathlib import Path


STANDALONE_APP = r'''import json
import os
import re
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
DATA = ROOT / "data"
DB = DATA / "leads.db"
PORT = int(os.getenv("PORT", "8080"))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def db():
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS leads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        interest TEXT NOT NULL,
        message TEXT NOT NULL,
        consent INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    return conn


def notify(payload):
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("SITE_LEAD_FROM", "").strip()
    to_email = os.getenv("SITE_LEAD_TO", "").strip()
    if not api_key or not from_email or not to_email:
        return
    body = {
        "from": from_email,
        "to": [to_email],
        "subject": f"Website enquiry: {payload['interest']}",
        "text": (
            f"Name: {payload['name']}\n"
            f"Email: {payload['email']}\n"
            f"Interest: {payload['interest']}\n\n"
            f"{payload['message']}"
        ),
    }
    req = Request(
        "https://api.resend.com/emails",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=10):
            pass
    except Exception:
        pass


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def json_response(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.json_response(200, {"ok": True})
            return
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/quote":
            self.json_response(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 20000:
            self.json_response(400, {"error": "Invalid request size."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.json_response(400, {"error": "Invalid JSON."})
            return

        name = str(payload.get("name") or "").strip()
        email = str(payload.get("email") or "").strip()
        interest = str(payload.get("interest") or "").strip()
        message = str(payload.get("message") or "").strip()
        consent = bool(payload.get("consent"))
        honeypot = str(payload.get("company_website") or "").strip()

        if honeypot:
            self.json_response(201, {"ok": True})
            return

        if not (2 <= len(name) <= 80):
            self.json_response(400, {"error": "Please enter your name."})
            return
        if not EMAIL_RE.match(email) or len(email) > 160:
            self.json_response(400, {"error": "Please enter a valid email."})
            return
        if not interest or len(interest) > 120:
            self.json_response(400, {"error": "Please choose an interest."})
            return
        if not (5 <= len(message) <= 2000):
            self.json_response(400, {"error": "Please add more project detail."})
            return
        if not consent:
            self.json_response(400, {"error": "Consent is required."})
            return

        conn = db()
        conn.execute(
            "INSERT INTO leads(name,email,interest,message,consent) VALUES(?,?,?,?,1)",
            (name, email, interest, message),
        )
        conn.commit()
        conn.close()

        notify(
            {
                "name": name,
                "email": email,
                "interest": interest,
                "message": message,
            }
        )
        self.json_response(201, {"ok": True})

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            page = SITE / "404.html"
            if page.exists():
                body = page.read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        return super().send_error(code, message, explain)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Customer website running on http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
'''


DOCKERFILE = """FROM python:3.12-slim
WORKDIR /app
COPY . /app
ENV PORT=8080
EXPOSE 8080
CMD ["python", "app.py"]
"""


DEPLOY_README = """# Standalone customer website package

This folder is a self-contained Python website application generated by Darwin Industries.

Local production-style test:
    python app.py

Open http://127.0.0.1:8080 and test the enquiry form.
Health check: /health

Lead storage:
Valid enquiries are stored in data/leads.db using SQLite.
For horizontally scaled hosting, replace SQLite with a managed database before scaling beyond one instance.

Optional lead email notifications:
Set RESEND_API_KEY, SITE_LEAD_FROM and SITE_LEAD_TO.
The website still records the lead if an email notification fails.

Container deployment:
    docker build -t customer-site .
    docker run --rm -p 8080:8080 customer-site

Launch safety:
Generated staging pages use noindex,nofollow. Do not remove that safeguard or point a live
customer domain at this package until the customer explicitly approves staging, factual/legal
copy is reviewed, asset rights are confirmed, real payment gates are satisfied, and a
backup/rollback plan exists.
"""


def export_deployment_package(project_root: Path, site_dir: Path) -> Path:
    deploy_dir = project_root / "deploy"
    deploy_site = deploy_dir / "site"
    deploy_dir.mkdir(parents=True, exist_ok=True)
    if deploy_site.exists():
        shutil.rmtree(deploy_site)
    shutil.copytree(site_dir, deploy_site)
    (deploy_dir / "app.py").write_text(STANDALONE_APP, encoding="utf-8")
    (deploy_dir / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    (deploy_dir / "README_DEPLOY.md").write_text(DEPLOY_README, encoding="utf-8")
    (deploy_dir / ".env.example").write_text(
        "PORT=8080\nRESEND_API_KEY=\nSITE_LEAD_FROM=\nSITE_LEAD_TO=\n",
        encoding="utf-8",
    )
    return deploy_dir
