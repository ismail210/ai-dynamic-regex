#!/usr/bin/env python3
"""Local HTTP server for A2/A7 human-review UI (validation only).

Serves the static tool and read/write of review JSON under accuracy_gold/.
Does not touch production APIs or inference.
"""

from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "validation_reports" / "human_review"))

from hr_lib import A2_REVIEW, A7_REVIEW, REPORT_DIR  # noqa: E402

TOOL_DIR = REPORT_DIR / "tool"
PORT = 8765

ALLOWED = {
    "/api/a2": A2_REVIEW,
    "/api/a7": A7_REVIEW,
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(TOOL_DIR), **kwargs)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ALLOWED:
            path = ALLOWED[parsed.path]
            self._json(200, json.loads(path.read_text(encoding="utf-8")))
            return
        if parsed.path == "/api/health":
            self._json(200, {"ok": True, "a2": str(A2_REVIEW), "a7": str(A7_REVIEW)})
            return
        return super().do_GET()

    def do_PUT(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ALLOWED:
            self._json(404, {"ok": False, "error": "not_found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return
        path = ALLOWED[parsed.path]
        # Preserve append-only review file; overwrite only the review dataset itself.
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._json(200, {"ok": True, "saved": str(path)})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> int:
    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"A2/A7 human review UI: http://127.0.0.1:{PORT}/")
    print(f"A2 dataset: {A2_REVIEW}")
    print(f"A7 dataset: {A7_REVIEW}")
    print("Ctrl+C to stop. Local only — no external network.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
