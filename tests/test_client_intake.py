import tempfile
import unittest
from pathlib import Path

import backend.storage as storage
from backend.client_intake import (
    INITIAL_QUESTIONS,
    _save_uploads,
    _seed_questions,
    assets_for_project,
    collect_client_answers,
)
from backend.storage import connect, init_db, now_iso


class ClientIntakeTests(unittest.TestCase):
    def test_uploaded_client_images_are_stored_with_categories(self):
        original_db_path = storage.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            storage.DB_PATH = Path(tmp) / "darwin-test.db"
            old_cwd = Path.cwd()
            try:
                import os
                os.chdir(tmp)
                conn = connect()
                init_db(conn)
                cur = conn.execute(
                    """INSERT INTO website_projects(
                        business_name,source_website,customer_email,mode,status,
                        quoted_price,currency,deposit_percent,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "Test Co",
                        "https://example.com",
                        "client@example.com",
                        "DEMO",
                        "CLIENT_INPUT_NEEDED",
                        179,
                        "USD",
                        100,
                        now_iso(),
                        now_iso(),
                    ),
                )
                project_id = int(cur.lastrowid)
                conn.commit()
                conn.close()

                saved = _save_uploads(
                    project_id,
                    [
                        ("hero_files", "hero.jpg", "image/jpeg", b"x" * 20000),
                        ("product_files", "product.webp", "image/webp", b"y" * 22000),
                    ],
                )
                self.assertEqual(saved, 2)
                assets = assets_for_project(project_id)
                self.assertEqual([a["category"] for a in assets], ["hero", "product"])
                self.assertTrue(Path(assets[0]["stored_path"]).exists())
            finally:
                os.chdir(old_cwd)
                storage.DB_PATH = original_db_path

    def test_completed_brief_returns_without_reopening_questionnaire(self):
        original_db_path = storage.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            storage.DB_PATH = Path(tmp) / "darwin-test.db"
            conn = connect()
            init_db(conn)
            cur = conn.execute(
                """INSERT INTO website_projects(
                    business_name,source_website,customer_email,mode,status,
                    quoted_price,currency,deposit_percent,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "Test Co",
                    "https://example.com",
                    "client@example.com",
                    "DEMO",
                    "CLIENT_INPUT_NEEDED",
                    1500,
                    "GBP",
                    50,
                    now_iso(),
                    now_iso(),
                ),
            )
            project_id = int(cur.lastrowid)
            conn.commit()
            conn.close()

            _seed_questions(project_id, INITIAL_QUESTIONS)

            conn = connect()
            for q in INITIAL_QUESTIONS:
                conn.execute(
                    """UPDATE website_client_questions
                    SET answer=?,status='ANSWERED',answered_at=?
                    WHERE project_id=? AND question_key=?""",
                    (f"answer for {q['key']}", now_iso(), project_id, q["key"]),
                )
            conn.commit()
            conn.close()

            # If this attempted to open/bind a questionnaire server the test would block.
            answers = collect_client_answers(
                project_id,
                "Test Co",
                questions=INITIAL_QUESTIONS,
                open_browser=False,
            )
            self.assertEqual(len(answers), len(INITIAL_QUESTIONS))
            self.assertEqual(
                answers["primary_goal"],
                "answer for primary_goal",
            )
        storage.DB_PATH = original_db_path


if __name__ == "__main__":
    unittest.main()
