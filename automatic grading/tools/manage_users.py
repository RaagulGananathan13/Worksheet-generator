"""Local operator account provisioning/recovery; never exposed over HTTP."""
import argparse
from datetime import datetime, timezone
from getpass import getpass
import os
from pathlib import Path
import re
import secrets
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.auth import hash_password
from app.database import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["add-teacher", "reset-password"])
    parser.add_argument("username")
    parser.add_argument("--name", help="Display name for a new teacher")
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._@+\-]{2,79}", username):
        parser.error("Username must contain 3–80 allowed letters/numbers/email characters.")
    if args.command == "add-teacher" and (not args.name or not 1 <= len(args.name.strip()) <= 100):
        parser.error("add-teacher requires --name with 1–100 characters.")
    directory = Path(os.getenv("AG_DATA_DIR", str(ROOT / "data"))).resolve()
    database = Database(directory)
    if not database.path.is_file():
        parser.error("Database not initialized. Start run.py once before using this tool.")
    existing = database.one("SELECT id FROM users WHERE username=?", (username,))
    if args.command == "add-teacher" and existing:
        parser.error("Username already exists.")
    if args.command == "reset-password" and not existing:
        parser.error("Username not found.")
    password = getpass("New password (10–128 characters): ")
    if not 10 <= len(password) <= 128 or password != getpass("Repeat password: "):
        parser.error("Passwords must match and contain 10–128 characters.")
    hashed = hash_password(password)
    with database.transaction() as connection:
        if args.command == "reset-password":
            connection.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed,existing["id"]))
            connection.execute("DELETE FROM sessions WHERE user_id=?", (existing["id"],))
        else:
            code = secrets.token_hex(5).upper()
            connection.execute("INSERT INTO users(id,name,username,password_hash,role,class_code,created_at) VALUES (?,?,?,?,?,?,?)",
                               (str(uuid4()),args.name.strip(),username,hashed,"teacher",code,datetime.now(timezone.utc).isoformat()))
    print("Teacher created. Class code: " + code if args.command == "add-teacher" else "Password changed. Existing sessions were revoked.")


if __name__ == "__main__":
    main()
