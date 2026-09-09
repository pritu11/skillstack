import unittest
from unittest.mock import MagicMock

import app


class TestSecurityHeaders(unittest.TestCase):
    def test_send_json_adds_security_headers(self):
        handler = app.FreelanceHandler.__new__(app.FreelanceHandler)
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()

        handler.send_json({"ok": True})

        sent = [(call.args[0], call.args[1]) for call in handler.send_header.call_args_list]
        self.assertIn(("X-Content-Type-Options", "nosniff"), sent)
        self.assertIn(("X-Frame-Options", "DENY"), sent)
        self.assertIn(("Referrer-Policy", "strict-origin-when-cross-origin"), sent)
        self.assertIn(("Permissions-Policy", "camera=(), microphone=(), geolocation=()"), sent)
        self.assertIn(("Content-Security-Policy", "default-src 'self'; object-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"), sent)
        self.assertIn(("Cache-Control", "no-store"), sent)


if __name__ == "__main__":
    unittest.main()
