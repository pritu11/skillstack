import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
LEADS_FILE = DATA_DIR / "leads.json"
PASSWORD_HASH = hashlib.sha256("12345".encode()).hexdigest()

users = json.loads(USERS_FILE.read_text())
existing_users = {user["email"] for user in users}
for index in range(1, 37):
    email = f"member{index}@skillstack.demo"
    if email not in existing_users:
        users.append({
            "email": email,
            "password": PASSWORD_HASH,
            "createdAt": (datetime.utcnow() - timedelta(days=index)).isoformat() + "Z"
        })

leads = json.loads(LEADS_FILE.read_text())
leads = leads[:40]
names = ["Aarav", "Diya", "Kabir", "Meera", "Riya", "Arjun", "Anaya", "Vihaan"]
goals = ["Build a portfolio", "Find first client", "Improve pricing", "Create a brand identity", "Launch a freelance service", "Learn client outreach"]
for index in range(len(leads) + 1, 41):
    leads.append({
        "name": names[index % len(names)],
        "email": f"member{1 + (index % 25)}@skillstack.demo",
        "goal": goals[index % len(goals)],
        "createdAt": (datetime.utcnow() - timedelta(hours=index)).isoformat() + "Z"
    })

USERS_FILE.write_text(json.dumps(users, indent=2) + "\n")
LEADS_FILE.write_text(json.dumps(leads, indent=2) + "\n")
print(f"Seeded {len(users)} users and {len(leads)} leads")
