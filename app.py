from flask import Flask, jsonify, render_template, request
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

app = Flask(__name__)
DB = Path("data/miniboard.db")


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (message_id)
                    REFERENCES messages(id) ON DELETE CASCADE
            )
        """)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/messages")
def get_messages():
    with connect() as con:
        messages = [
            dict(row) for row in
            con.execute("SELECT * FROM messages ORDER BY id DESC").fetchall()
        ]

        replies = con.execute(
            "SELECT * FROM replies ORDER BY id ASC"
        ).fetchall()

    # それぞれのコメントに返信を紐づける
    replies_by_message = {}
    for reply in replies:
        reply_data = dict(reply)
        message_id = reply_data["message_id"]
        replies_by_message.setdefault(message_id, []).append(reply_data)

    for message in messages:
        message["replies"] = replies_by_message.get(message["id"], [])

    return jsonify(messages)


@app.post("/api/messages")
def create_message():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()[:30]
    message = str(data.get("message", "")).strip()[:300]

    if not name or not message:
        return jsonify({"error": "name and message are required"}), 400

    created_at = datetime.now(timezone.utc).isoformat()

    with connect() as con:
        cur = con.execute(
            """INSERT INTO messages(name, message, created_at)
               VALUES (?, ?, ?)""",
            (name, message, created_at)
        )
        row = con.execute(
            "SELECT * FROM messages WHERE id = ?",
            (cur.lastrowid,)
        ).fetchone()

    return jsonify(dict(row)), 201


@app.post("/api/messages/<int:message_id>/replies")
def create_reply(message_id):
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()[:30]
    message = str(data.get("message", "")).strip()[:300]

    if not name or not message:
        return jsonify({"error": "name and message are required"}), 400

    created_at = datetime.now(timezone.utc).isoformat()

    with connect() as con:
        original = con.execute(
            "SELECT id FROM messages WHERE id = ?",
            (message_id,)
        ).fetchone()

        if original is None:
            return jsonify({"error": "message not found"}), 404

        cur = con.execute(
            """INSERT INTO replies(message_id, name, message, created_at)
               VALUES (?, ?, ?, ?)""",
            (message_id, name, message, created_at)
        )

        row = con.execute(
            "SELECT * FROM replies WHERE id = ?",
            (cur.lastrowid,)
        ).fetchone()

    return jsonify(dict(row)), 201


@app.put("/api/messages/<int:message_id>")
def update_message(message_id):
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()[:300]

    if not message:
        return jsonify({"error": "message is required"}), 400

    with connect() as con:
        cur = con.execute(
            "UPDATE messages SET message = ? WHERE id = ?",
            (message, message_id)
        )
        if cur.rowcount == 0:
            return jsonify({"error": "not found"}), 404

    return jsonify({"ok": True})


@app.delete("/api/messages/<int:message_id>")
def delete_message(message_id):
    with connect() as con:
        cur = con.execute(
            "DELETE FROM messages WHERE id = ?",
            (message_id,)
        )
        if cur.rowcount == 0:
            return jsonify({"error": "not found"}), 404

    return "", 204


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
