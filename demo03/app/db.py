import sqlite3
from pathlib import Path

from flask import current_app, g, has_request_context, session
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = Path(current_app.root_path).parent / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)


def ensure_default_users():
    db = get_db()
    users = [
        ("admin", "admin123", "admin"),
        ("viewer", "viewer123", "viewer"),
    ]
    for username, password, role in users:
        exists = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if not exists:
            db.execute(
                "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
    db.commit()


def log_operation(action, detail="", username=None):
    db = get_db()
    actor = username or "system"
    if username is None and has_request_context():
        actor = session.get("username") or "system"
    db.execute(
        "INSERT INTO operation_logs(username, action, detail) VALUES (?, ?, ?)",
        (actor, action, detail),
    )
    db.commit()


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_dicts(rows):
    return [dict(row) for row in rows]
