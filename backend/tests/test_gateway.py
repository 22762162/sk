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
        self.assertEqual(kwargs["timeout"].read, 180.0)

    def test_total_elapsed_time_does_not_cancel_a_responsive_retry(self) -> None:
        transient = Mock(status_code=503, text="synthetic busy")
        response = Mock(status_code=200)
        response.json.return_value = {
            "modelVersion": "gemini-3.6-flash",
            "candidates": [{"content": {"parts": [{"text": "{\"ok\":true}"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {},
        }
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic-key"}), \
                patch.object(gateway, "MANIFEST_DIR", Path(temp_dir)), \
                patch.object(gateway.httpx, "post", side_effect=[transient, response]) as post, \
                patch.object(gateway.time, "sleep"), \
                patch.object(gateway.time, "monotonic", side_effect=[0.0, 181.0]) as monotonic:
            result = gateway.call("gemini", "gemini-3.6-flash", "system", "user")

        self.assertEqual(result["text"], '{"ok":true}')
        self.assertEqual(post.call_count, 2)
        monotonic.assert_not_called()

    def test_180_seconds_without_response_data_stops_without_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic-key"}), \
                patch.object(gateway, "MANIFEST_DIR", Path(temp_dir)), \
                patch.object(gateway.httpx, "post",
                             side_effect=gateway.httpx.ReadTimeout("synthetic idle")) as post:
            with self.assertRaisesRegex(gateway.GatewayError, "连续 180 秒未收到响应数据"):
                gateway.call("gemini", "gemini-3.6-flash", "system", "user")

        self.assertEqual(post.call_count, 1)

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

    def test_openai_is_available_for_bakeoff_without_joining_runtime_three(self) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "model": "gpt-5.6-sol",
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4},
        }
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-key"}), \
                patch.object(gateway, "MANIFEST_DIR", Path(temp_dir)), \
                patch.object(gateway.httpx, "post", return_value=response) as post:
            result = gateway.call(
                "openai", "gpt-5.6-sol", "system", "user",
                max_tokens=222, temperature=0.0,
            )

        self.assertEqual(result["text"], '{"ok":true}')
        self.assertEqual(post.call_args.args[0], "https://api.openai.com/v1/chat/completions")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["max_completion_tokens"], 222)
        self.assertNotIn("temperature", payload)


if __name__ == "__main__":
    unittest.main()
