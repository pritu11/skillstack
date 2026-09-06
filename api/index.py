import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder='..', static_url_path='')

# Simple in-memory store for demo purposes.
DATA = {"users": [], "leads": []}


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

    if any(user.get('email') == email for user in DATA['users']):
        return jsonify({"ok": False, "message": "Email already exists"}), 409

    DATA['users'].append({
        'email': email,
        'password': hash_password(password),
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    })
    token = uuid.uuid4().hex
    return jsonify({"ok": True, "token": token, "user": {"email": email}})


@app.post('/api/login')
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    password = (payload.get('password') or '').strip()

    user = next((u for u in DATA['users'] if u.get('email') == email), None)
    if not user or user.get('password') != hash_password(password):
        return jsonify({"ok": False, "message": "Invalid email or password"}), 401

    token = uuid.uuid4().hex
    return jsonify({"ok": True, "token": token, "user": {"email": email}})


@app.post('/api/lead')
def lead():
    token = request.headers.get('Authorization', '')
    if not token:
        return jsonify({"ok": False, "message": "Login required"}), 401

    payload = request.get_json(silent=True) or {}
    DATA['leads'].append({
        'name': (payload.get('name') or 'Anonymous').strip(),
        'goal': (payload.get('goal') or 'General help').strip(),
        'email': (payload.get('email') or 'visitor@example.com').strip(),
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    })
    return jsonify({"ok": True, "message": "Your request has been saved"})


@app.get('/api/dashboard')
def dashboard():
    return jsonify({
        'ok': True,
        'user': None,
        'stats': {
            'users': len(DATA['users']),
            'leads': len(DATA['leads']),
            'latest': DATA['leads'][-3:][::-1] if DATA['leads'] else []
        }
    })


@app.get('/')
def root():
    return send_from_directory('..', 'index.html')


@app.get('/<path:path>')
def static_path(path):
    return send_from_directory('..', path)
