"""The optional API access key protects every route of a hosted backend but health."""

from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest import mock

from fastapi.testclient import TestClient

from app import app
from config import Settings, settings

ORIGIN = "http://localhost:5173"  # in the default CORS allow-list


def _token(value):
    return mock.patch("app.settings", replace(settings, api_access_token=value))


class AccessTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_open_when_no_token_is_configured(self):
        with _token(None):
            self.assertEqual(self.client.get("/api/documents/doc_0000000000000000").status_code, 404)

    def test_requires_the_bearer_token_on_api_and_upload_routes(self):
        with _token("s3cret"):
            for path in ("/api/documents/doc_0000000000000000", "/upload"):
                denied = self.client.get(path, headers={"Origin": ORIGIN})
                self.assertEqual(denied.status_code, 401, path)
                # Readable by the browser: CORS headers are still present.
                self.assertEqual(denied.headers.get("access-control-allow-origin"), ORIGIN)
            wrong = self.client.get(
                "/api/documents/doc_0000000000000000",
                headers={"Authorization": "Bearer nope"},
            )
            self.assertEqual(wrong.status_code, 401)
            allowed = self.client.get(
                "/api/documents/doc_0000000000000000",
                headers={"Authorization": "Bearer s3cret"},
            )
            self.assertEqual(allowed.status_code, 404)

    def test_every_route_but_health_is_protected(self):
        with _token("s3cret"):
            for path in ("/", "/openapi.json", "/docs"):
                self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_preflight_and_health_need_no_token(self):
        with _token("s3cret"):
            preflight = self.client.options(
                "/api/documents",
                headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(self.client.get("/health/live").status_code, 200)

    def test_origin_regex_and_token_are_read_from_the_environment(self):
        env = {
            "CORS_ALLOW_ORIGIN_REGEX": r"^https://estima3d-[a-z0-9-]+\.vercel\.app$",
            "API_ACCESS_TOKEN": "s3cret",
        }
        with mock.patch.dict(os.environ, env):
            configured = Settings()
        self.assertEqual(configured.cors_allow_origin_regex, env["CORS_ALLOW_ORIGIN_REGEX"])
        self.assertEqual(configured.api_access_token, "s3cret")


if __name__ == "__main__":
    unittest.main()
