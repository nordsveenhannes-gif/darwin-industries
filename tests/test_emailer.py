import unittest

from backend.emailer import _ensure_opt_out, is_safe_business_email


class EmailGuardrailTests(unittest.TestCase):
    def test_accepts_role_email_on_same_domain(self):
        self.assertTrue(
            is_safe_business_email("info@example.se", "https://www.example.se")
        )

    def test_accepts_local_language_role_email(self):
        self.assertTrue(
            is_safe_business_email("kontakt@example.no", "https://example.no")
        )

    def test_rejects_named_person_email(self):
        self.assertFalse(
            is_safe_business_email("anna.andersson@example.se", "https://example.se")
        )

    def test_rejects_other_domain(self):
        self.assertFalse(
            is_safe_business_email("info@other.se", "https://example.se")
        )

    def test_opt_out_is_added_once(self):
        body = "Hello. We noticed one website improvement."
        result = _ensure_opt_out(body)
        self.assertIn("no thanks", result.lower())
        self.assertEqual(_ensure_opt_out(result), result)


if __name__ == "__main__":
    unittest.main()
