import tempfile
import unittest
from pathlib import Path

import backend.storage as storage
from backend.client_intake import INITIAL_QUESTIONS, _seed_questions, collect_client_answers
from backend.storage import connect, init_db, now_iso


class ClientIntakeTests(unittest.TestCase):
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
