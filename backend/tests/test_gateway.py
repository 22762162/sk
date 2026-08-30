from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consult-engine"))
import gateway  # noqa: E402


class GeminiGatewayTest(unittest.TestCase):
    def test_gemini_native_request_and_response_mapping(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "modelVersion": "gemini-3.6-flash",
            "candidates": [{
                "content": {"parts": [{"text": "{\"ok\":true}"}]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 5},
        }
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic-key"}), \
                patch.object(gateway, "MANIFEST_DIR", Path(temp_dir)), \
                patch.object(gateway.httpx, "post", return_value=response) as post:
            result = gateway.call(
                "gemini", "gemini-3.6-flash", "system synthetic", "user synthetic",
                max_tokens=321, temperature=0.0, output_schema_version="synthetic-v1",
            )

        self.assertEqual(result["text"], '{"ok":true}')
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(
            url,
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-3.6-flash:generateContent",
        )
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "synthetic-key")
        self.assertEqual(
            kwargs["json"]["system_instruction"]["parts"][0]["text"],
            "system synthetic",
        )
        self.assertEqual(kwargs["json"]["contents"][0]["parts"][0]["text"], "user synthetic")
        self.assertEqual(kwargs["json"]["generationConfig"], {"maxOutputTokens": 321})
        self.assertNotIn("temperature", kwargs["json"]["generationConfig"])

    def test_gemini_empty_candidate_fails_closed(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "modelVersion": "gemini-3.6-flash",
            "candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}],
        }
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic-key"}), \
                patch.object(gateway, "MANIFEST_DIR", Path(temp_dir)), \
                patch.object(gateway.httpx, "post", return_value=response):
            with self.assertRaisesRegex(gateway.GatewayError, "未返回正文:SAFETY"):
                gateway.call("gemini", "gemini-3.6-flash", "system", "user")


if __name__ == "__main__":
    unittest.main()
