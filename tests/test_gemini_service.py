"""
Unit and Integration Tests for GeminiService and connection handling.
"""

import os
import unittest
from services.gemini_service import GeminiService


class TestGeminiService(unittest.TestCase):
    def test_missing_api_key_status(self):
        svc = GeminiService(api_key="")
        res = svc.test_connection()
        self.assertEqual(res["status"], "MISSING_KEY")
        self.assertIn("missing", res["message"].lower())
        self.assertEqual(svc.get_masked_key(), "Not Configured")

    def test_masked_key_formatting(self):
        svc = GeminiService(api_key="AIzaSyA1234567890abcdefXYZ")
        masked = svc.get_masked_key()
        self.assertTrue(masked.startswith("AIza"))
        self.assertTrue(masked.endswith("tXYZ") or masked.endswith("fXYZ"))
        self.assertIn("••••••••", masked)
        # Verify full key is not exposed
        self.assertNotIn("1234567890", masked)

    def test_configurable_model(self):
        svc = GeminiService(api_key="dummy_key", model="gemini-3.5-flash-lite")
        self.assertEqual(svc.model, "gemini-3.5-flash-lite")

    def test_live_connection_if_key_available(self):
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            self.skipTest("No GEMINI_API_KEY set; skipping live network test.")
        svc = GeminiService(api_key=key, model="gemini-3.5-flash")
        res = svc.test_connection()
        # Should be SUCCESS if network permits, or a handled status (NETWORK_ERROR / INVALID_KEY)
        self.assertIn(res["status"], ["SUCCESS", "NETWORK_ERROR", "INVALID_KEY", "QUOTA_EXHAUSTED", "SERVICE_UNAVAILABLE"])


if __name__ == "__main__":
    unittest.main()
