import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

import backend.storage as storage
from backend.site_server import StagingHandler
from http.server import ThreadingHTTPServer


class WebsiteServerTests(unittest.TestCase):
    def test_custom_404_page_is_served(self):
        original_db_path = storage.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
            (site / "404.html").write_text("<html><body>branded missing page</body></html>", encoding="utf-8")
            storage.DB_PATH = root / "darwin-test.db"

            handler = type(
                "MissingPageHandler",
                (StagingHandler,),
                {"site_dir": site, "project_id": None},
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                try:
                    urlopen(f"http://127.0.0.1:{server.server_port}/does-not-exist", timeout=5)
                    self.fail("Expected an HTTP 404")
                except Exception as exc:
                    response = getattr(exc, "read", None)
                    self.assertIsNotNone(response)
                    body = exc.read().decode("utf-8")
                    self.assertIn("branded missing page", body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                storage.DB_PATH = original_db_path

    def test_honeypot_submission_is_not_persisted(self):
        original_db_path = storage.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
            storage.DB_PATH = root / "darwin-test.db"

            handler = type(
                "BotTestStagingHandler",
                (StagingHandler,),
                {"site_dir": site, "project_id": None},
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                payload = json.dumps(
                    {
                        "name": "Bot",
                        "email": "bot@example.com",
                        "interest": "Something",
                        "message": "Automated spam message",
                        "consent": True,
                        "company_website": "https://spam.invalid",
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/quote",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 201)

                conn = storage.connect()
                storage.init_db(conn)
                count = conn.execute("SELECT COUNT(*) AS n FROM website_leads").fetchone()["n"]
                conn.close()
                self.assertEqual(count, 0)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                storage.DB_PATH = original_db_path

    def test_quote_form_post_is_persisted(self):
        original_db_path = storage.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
            storage.DB_PATH = root / "darwin-test.db"

            handler = type(
                "TestStagingHandler",
                (StagingHandler,),
                {"site_dir": site, "project_id": None},
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                payload = json.dumps(
                    {
                        "name": "Demo Customer",
                        "email": "customer@example.com",
                        "interest": "Infrared sauna",
                        "message": "I would like pricing for a home project.",
                        "consent": True,
                    }
                ).encode("utf-8")
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/quote",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 201)
                    body = json.loads(response.read().decode("utf-8"))
                    self.assertTrue(body["ok"])

                conn = storage.connect()
                storage.init_db(conn)
                count = conn.execute("SELECT COUNT(*) AS n FROM website_leads").fetchone()["n"]
                conn.close()
                self.assertEqual(count, 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                storage.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
