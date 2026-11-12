#!/usr/bin/env python3
"""
DocUrgent 24/7 — Vercel Python Serverless Entrypoint
Reconstructs rewritten API routes cleanly and wraps DocUrgentHTTPHandler.
"""

import os
import sys
import urllib.parse

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server


class handler(server.DocUrgentHTTPHandler):
    def _normalize_vercel_path(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "__dp" in params and params["__dp"]:
            target_path = params.pop("__dp")[0]
            if not target_path.startswith("/"):
                target_path = "/" + target_path
            remaining_qs = urllib.parse.urlencode(params, doseq=True)
            self.path = f"{target_path}?{remaining_qs}" if remaining_qs else target_path

    def list_directory(self, path):
        self.send_error_json(404, "Endpoint not found")
        return None

    def do_GET(self):
        self._normalize_vercel_path()
        if self.path.startswith("/api/") or self.path.startswith("/uploads/"):
            return super().do_GET()
        return self.send_error_json(404, "API endpoint not found")

    def do_POST(self):
        self._normalize_vercel_path()
        return super().do_POST()

    def do_OPTIONS(self):
        self._normalize_vercel_path()
        return super().do_OPTIONS()
