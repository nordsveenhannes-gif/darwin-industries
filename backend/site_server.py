from __future__ import annotations

import argparse
import json
import re
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from backend.storage import connect, init_db, now_iso


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StagingHandler(SimpleHTTPRequestHandler):
    site_dir: Path = Path(".")
    project_id: int | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.site_dir), **kwargs)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/quote":
            self._json(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 20000:
            self._json(400, {"error": "Invalid request size."})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self._json(400, {"error": "Invalid JSON."})
            return

        name = str(payload.get("name") or "").strip()
        email = str(payload.get("email") or "").strip()
        interest = str(payload.get("interest") or "").strip()
        message = str(payload.get("message") or "").strip()
        consent = bool(payload.get("consent"))

        if not (2 <= len(name) <= 80):
            self._json(400, {"error": "Please enter your name."})
            return
        if not EMAIL_RE.match(email) or len(email) > 160:
            self._json(400, {"error": "Please enter a valid email."})
            return
        if not interest or len(interest) > 120:
            self._json(400, {"error": "Please choose a product interest."})
            return
        if not (5 <= len(message) <= 2000):
            self._json(400, {"error": "Please add a little more detail about the project."})
            return
        if not consent:
            self._json(400, {"error": "Consent is required to submit this enquiry."})
            return

        conn = connect()
        init_db(conn)
        conn.execute(
            """
            INSERT INTO website_leads(
                project_id, name, email, interest, message, consent, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 1, 'NEW', ?)
            """,
            (self.project_id, name, email, interest, message, now_iso()),
        )
        conn.commit()
        conn.close()

        self._json(201, {"ok": True, "message": "Enquiry recorded."})

    def log_message(self, format, *args):
        return


def serve_site(site_dir: Path, project_id: int | None, port: int = 8788, open_browser: bool = False) -> None:
    site_dir = site_dir.resolve()
    if not (site_dir / "index.html").exists():
        raise RuntimeError(f"No built site found at {site_dir}")

    handler = type(
        "ProjectStagingHandler",
        (StagingHandler,),
        {"site_dir": site_dir, "project_id": project_id},
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"\n=== CUSTOMER STAGING SITE ===")
    print(f"Preview: http://127.0.0.1:{port}")
    print("Quote form: LIVE for local staging; submissions are stored in Darwin's database.")
    print("Public internet deployment: NOT enabled.")
    print("Press Ctrl+C to stop the preview.\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStaging preview stopped.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a Darwin customer staging website.")
    parser.add_argument("--site-dir", required=True)
    parser.add_argument("--project-id", type=int)
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    serve_site(
        Path(args.site_dir),
        args.project_id,
        max(1024, min(args.port, 65535)),
        open_browser=args.open_browser,
    )


if __name__ == "__main__":
    main()
