import hashlib
import hmac
import json
import os
import re
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from supabase import create_client
except ImportError:
    create_client = None

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
USERS_FILE = DATA_DIR / 'users.json'
LEADS_FILE = DATA_DIR / 'leads.json'
SESSIONS_FILE = DATA_DIR / 'sessions.json'
TOKEN_SECRET = os.environ.get('SKILLSTACK_TOKEN_SECRET', 'skillstack-demo-secret')
ADMIN_KEY = os.environ.get('SKILLSTACK_ADMIN_KEY', 'admin-demo-key')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if create_client and SUPABASE_URL and SUPABASE_KEY else None
except Exception:
    supabase = None

DATA_DIR.mkdir(exist_ok=True)
for file_path in (USERS_FILE, LEADS_FILE, SESSIONS_FILE):
    if not file_path.exists():
        file_path.write_text('[]', encoding='utf-8')

app = Flask(__name__, static_folder=str(ROOT), static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault('Content-Security-Policy', "default-src 'self'; object-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'")
    response.headers.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
    response.headers.setdefault('Cache-Control', 'no-store')
    response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response


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


def database_users():
    if supabase:
        try:
            rows = supabase.table('users').select('email,password,created_at').execute().data or []
            return [{'email': row['email'], 'password': row['password'], 'createdAt': row['created_at']} for row in rows]
        except Exception:
            pass
    return load_json(USERS_FILE)


def database_add_user(user):
    if supabase:
        try:
            supabase.table('users').insert({
                'email': user['email'],
                'password': user['password'],
                'created_at': user['createdAt']
            }).execute()
            return
        except Exception:
            pass
    save_json(USERS_FILE, load_json(USERS_FILE) + [user])


def database_leads():
    if supabase:
        try:
            rows = supabase.table('leads').select('name,email,goal,created_at').order('created_at', desc=True).execute().data or []
            return [{'name': row['name'], 'email': row['email'], 'goal': row['goal'], 'createdAt': row['created_at']} for row in rows]
        except Exception:
            pass
    return load_json(LEADS_FILE)


def database_add_lead(lead_data):
    if supabase:
        supabase.table('leads').insert({
            'name': lead_data['name'],
            'email': lead_data['email'],
            'goal': lead_data['goal'],
            'created_at': lead_data['createdAt']
        }).execute()
        return
    save_json(LEADS_FILE, load_json(LEADS_FILE) + [lead_data])


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def password_matches(stored_password: str, password: str) -> bool:
    if stored_password.startswith(('pbkdf2:', 'scrypt:')):
        return check_password_hash(stored_password, password)
    legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    return hmac.compare_digest(stored_password, legacy_hash)


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

    if not email or not is_valid_email(email) or len(password) < 8:
        return jsonify({"ok": False, "message": "Please provide a valid email and password"}), 400

    users = database_users()
    if any(user.get('email') == email for user in users):
        return jsonify({"ok": False, "message": "Email already exists"}), 409

    user = {
        'email': email,
        'password': hash_password(password),
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    }
    database_add_user(user)
    token = create_session(email)
    return jsonify({"ok": True, "token": token, "user": {"email": email}})


@app.post('/api/login')
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    password = (payload.get('password') or '').strip()

    users = database_users()
    user = next((u for u in users if u.get('email') == email), None)
    if not user or not password_matches(user.get('password', ''), password):
        return jsonify({"ok": False, "message": "Invalid email or password"}), 401

    if not user.get('password', '').startswith(('pbkdf2:', 'scrypt:')):
        user['password'] = hash_password(password)
        save_json(USERS_FILE, [user if item.get('email') == email else item for item in users])

    token = create_session(email)
    return jsonify({"ok": True, "token": token, "user": {"email": email}})


@app.post('/api/lead')
def lead():
    payload = request.get_json(silent=True) or {}
    token = payload.get('token') or request.headers.get('Authorization', '')
    email = get_user_from_token(token.strip())
    if not email:
        return jsonify({"ok": False, "message": "Login required"}), 401

    lead_data = {
        'name': (payload.get('name') or 'Anonymous').strip()[:120],
        'goal': (payload.get('goal') or 'General help').strip()[:500],
        'email': email,
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    }
    database_add_lead(lead_data)
    return jsonify({"ok": True, "message": "Your request has been saved"})


@app.get('/api/dashboard')
def dashboard():
    token = request.headers.get('Authorization', '').strip()
    email = get_user_from_token(token)
    if not email:
        return jsonify({'ok': False, 'message': 'Login required'}), 401
    users = database_users()
    leads = database_leads()
    return jsonify({
        'ok': True,
        'user': {'email': email} if email else None,
        'stats': {
            'users': len(users),
            'leads': len(leads),
            'latest': leads[-3:][::-1] if leads else []
        }
    })


@app.get('/api/admin/data')
def admin_data():
    if not ADMIN_KEY or not hmac.compare_digest(request.headers.get('X-Admin-Key', ''), ADMIN_KEY):
        return jsonify({'ok': False, 'message': 'Admin access required'}), 401

    users = database_users()
    leads = database_leads()
    return jsonify({
        'ok': True,
        'users': users,
        'leads': leads,
        'stats': {'users': len(users), 'leads': len(leads)}
    })


def create_session(email: str) -> str:
    expires_at = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    payload = urlsafe_b64encode(json.dumps({'email': email, 'exp': expires_at}).encode()).decode().rstrip('=')
    signature = hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f'{payload}.{signature}'

    sessions = load_json(SESSIONS_FILE)
    sessions.append({
        'token': token,
        'email': email,
        'createdAt': datetime.utcnow().isoformat() + 'Z',
        'expiresAt': expires_at,
    })
    save_json(SESSIONS_FILE, sessions)
    return token


def get_user_from_token(token: str):
    sessions = load_json(SESSIONS_FILE)
    session = next((item for item in sessions if item.get('token') == token), None)
    if session:
        expires_at = session.get('expiresAt')
        try:
            if isinstance(expires_at, (int, float)) and expires_at < datetime.now(timezone.utc).timestamp():
                return None
        except Exception:
            pass
        email = session.get('email')
        if isinstance(email, str) and is_valid_email(email):
            return email

    try:
        payload, signature = token.split('.', 1)
        expected = hmac.new(TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padded_payload = payload + '=' * (-len(payload) % 4)
        session_data = json.loads(urlsafe_b64decode(padded_payload).decode())
        if session_data.get('exp', 0) < datetime.now(timezone.utc).timestamp():
            return None
        email = session_data.get('email')
        return email if isinstance(email, str) and is_valid_email(email) else None
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


@app.get('/')
def root():
    return send_from_directory(str(ROOT), 'index.html')


@app.get('/<path:path>')
def static_path(path):
    return send_from_directory(str(ROOT), path)
