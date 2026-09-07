import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"
LEADS_FILE = DATA_DIR / "leads.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
ADMIN_KEY = os.environ.get("SKILLSTACK_ADMIN_KEY", "admin-demo-key")

DATA_DIR.mkdir(exist_ok=True)
for file_path in [USERS_FILE, LEADS_FILE, SESSIONS_FILE]:
    if not file_path.exists():
        file_path.write_text("[]", encoding="utf-8")


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else []


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def is_valid_email(email: str) -> bool:
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))


class FreelanceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self.send_json({"ok": True, "message": "Server running"})
            return

        if path == "/api/dashboard":
            token = self.headers.get("Authorization", "")
            self.send_json(self.get_dashboard(token))
            return

        if path == "/api/admin/data":
            if self.headers.get("X-Admin-Key", "") != ADMIN_KEY:
                self.send_json({"ok": False, "message": "Admin access required"}, 401)
                return
            users = load_json(USERS_FILE, [])
            leads = load_json(LEADS_FILE, [])
            self.send_json({"ok": True, "users": users, "leads": leads, "stats": {"users": len(users), "leads": len(leads)}})
            return

        self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_json({"ok": False, "message": "Invalid JSON"}, 400)
            return

        if path == "/api/signup":
            self.handle_signup(payload)
        elif path == "/api/login":
            self.handle_login(payload)
        elif path == "/api/lead":
            self.handle_lead(payload)
        else:
            self.send_json({"ok": False, "message": "Not found"}, 404)

    def serve_static(self, path: str):
        if path in ["/", ""]:
            path = "/index.html"

        safe_path = (ROOT / path.lstrip("/")).resolve()
        if not str(safe_path).startswith(str(ROOT)):
            self.send_json({"ok": False, "message": "Invalid path"}, 403)
            return

        if safe_path.is_dir():
            safe_path = safe_path / "index.html"

        if safe_path.exists() and safe_path.is_file():
            content = safe_path.read_bytes()
            ext = safe_path.suffix.lower()
            mime = "text/html" if ext == ".html" else "application/javascript" if ext == ".js" else "text/css" if ext == ".css" else "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_json({"ok": False, "message": "Not found"}, 404)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_signup(self, payload):
        email = (payload.get("email") or "").strip().lower()
        password = (payload.get("password") or "").strip()

        if not email or not is_valid_email(email) or not password or len(password) < 4:
            self.send_json({"ok": False, "message": "Please provide a valid email and a password with at least 4 characters"}, 400)
            return

        users = load_json(USERS_FILE, [])
        if any(user.get("email") == email for user in users):
            self.send_json({"ok": False, "message": "Email already exists"}, 409)
            return

        users.append({
            "email": email,
            "password": hash_password(password),
            "createdAt": datetime.utcnow().isoformat() + "Z"
        })
        save_json(USERS_FILE, users)
        token = self.create_session(email)
        self.send_json({"ok": True, "token": token, "user": {"email": email}})

    def handle_login(self, payload):
        email = (payload.get("email") or "").strip().lower()
        password = (payload.get("password") or "").strip()

        users = load_json(USERS_FILE, [])
        user = next((u for u in users if u.get("email") == email), None)

        if not user or user.get("password") != hash_password(password):
            self.send_json({"ok": False, "message": "Invalid email or password"}, 401)
            return

        token = self.create_session(email)
        self.send_json({"ok": True, "token": token, "user": {"email": email}})

    def handle_lead(self, payload):
        token = (payload.get("token") or self.headers.get("Authorization", "")).strip()
        email = self.get_user_from_token(token)
        if not email:
            self.send_json({"ok": False, "message": "Login required"}, 401)
            return

        leads = load_json(LEADS_FILE, [])
        leads.append({
            "name": (payload.get("name") or "Anonymous").strip(),
            "email": (payload.get("email") or email).strip(),
            "goal": (payload.get("goal") or "General help").strip(),
            "createdAt": datetime.utcnow().isoformat() + "Z"
        })
        save_json(LEADS_FILE, leads)
        self.send_json({"ok": True, "message": "Your request has been saved"})

    def create_session(self, email: str) -> str:
        sessions = load_json(SESSIONS_FILE, [])
        token = uuid.uuid4().hex
        sessions.append({"token": token, "email": email})
        save_json(SESSIONS_FILE, sessions)
        return token

    def get_user_from_token(self, token: str):
        sessions = load_json(SESSIONS_FILE, [])
        for session in sessions:
            if session.get("token") == token:
                return session.get("email")
        return None

    def get_dashboard(self, token: str):
        email = self.get_user_from_token(token)
        users = load_json(USERS_FILE, [])
        leads = load_json(LEADS_FILE, [])
        return {
            "ok": True,
            "user": {"email": email} if email else None,
            "stats": {
                "users": len(users),
                "leads": len(leads),
                "latest": leads[-3:][::-1] if leads else []
            }
        }

    def log_message(self, format, *args):
        return


def main():
    server = ThreadingHTTPServer(("0.0.0.0", 8000), FreelanceHandler)
    print("Server running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
