import hashlib
import hmac
import json
import os
import re
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
USERS_FILE = DATA_DIR / 'users.json'
LEADS_FILE = DATA_DIR / 'leads.json'
SESSIONS_FILE = DATA_DIR / 'sessions.json'
TOKEN_SECRET = os.environ.get('SKILLSTACK_TOKEN_SECRET', 'skillstack-demo-secret')

DATA_DIR.mkdir(exist_ok=True)
for file_path in (USERS_FILE, LEADS_FILE, SESSIONS_FILE):
    if not file_path.exists():
        file_path.write_text('[]', encoding='utf-8')

app = Flask(__name__, static_folder=str(ROOT), static_url_path='')


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []


def save_json(path: Path, data):
    try:
        path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    except OSError:
        pass


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def is_valid_email(email: str) -> bool:
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))


@app.get('/api/health')
def health():
    return jsonify({"ok": True, "message": "Server running"})


@app.post('/api/signup')
def signup():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    password = (payload.get('password') or '').strip()

    if not email or not is_valid_email(email) or len(password) < 4:
        return jsonify({"ok": False, "message": "Please provide a valid email and password"}), 400

    users = load_json(USERS_FILE)
    if any(user.get('email') == email for user in users):
        return jsonify({"ok": False, "message": "Email already exists"}), 409

    users.append({
        'email': email,
        'password': hash_password(password),
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    })
    save_json(USERS_FILE, users)
    token = create_session(email)
    return jsonify({"ok": True, "token": token, "user": {"email": email}})


@app.post('/api/login')
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    password = (payload.get('password') or '').strip()

    users = load_json(USERS_FILE)
    user = next((u for u in users if u.get('email') == email), None)
    if not user or user.get('password') != hash_password(password):
        return jsonify({"ok": False, "message": "Invalid email or password"}), 401

    token = create_session(email)
    return jsonify({"ok": True, "token": token, "user": {"email": email}})


@app.post('/api/lead')
def lead():
    token = (request.get_json(silent=True) or {}).get('token') or request.headers.get('Authorization', '')
    email = get_user_from_token(token.strip())
    if not email:
        return jsonify({"ok": False, "message": "Login required"}), 401

    payload = request.get_json(silent=True) or {}
    leads = load_json(LEADS_FILE)
    leads.append({
        'name': (payload.get('name') or 'Anonymous').strip(),
        'goal': (payload.get('goal') or 'General help').strip(),
        'email': (payload.get('email') or email).strip(),
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    })
    save_json(LEADS_FILE, leads)
    return jsonify({"ok": True, "message": "Your request has been saved"})


@app.get('/api/dashboard')
def dashboard():
    token = request.headers.get('Authorization', '').strip()
    email = get_user_from_token(token)
    users = load_json(USERS_FILE)
    leads = load_json(LEADS_FILE)
    return jsonify({
        'ok': True,
        'user': {'email': email} if email else None,
        'stats': {
            'users': len(users),
            'leads': len(leads),
            'latest': leads[-3:][::-1] if leads else []
        }
    })


def create_session(email: str) -> str:
    payload = urlsafe_b64encode(json.dumps({'email': email}).encode()).decode().rstrip('=')
    signature = hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def get_user_from_token(token: str):
    sessions = load_json(SESSIONS_FILE)
    session = next((item for item in sessions if item.get('token') == token), None)
    if session:
        return session.get('email')

    try:
        payload, signature = token.split('.', 1)
        expected = hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padded_payload = payload + '=' * (-len(payload) % 4)
        email = json.loads(urlsafe_b64decode(padded_payload).decode()).get('email')
        return email if isinstance(email, str) and is_valid_email(email) else None
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


@app.get('/')
def root():
    return send_from_directory(str(ROOT), 'index.html')


@app.get('/<path:path>')
def static_path(path):
    return send_from_directory(str(ROOT), path)
