
"""Reaction API, kept separate from existing message and reply routes."""

from contextlib import closing
from uuid import UUID

from flask import Blueprint, jsonify, request

DEFAULT_REACTIONS = (
    ("empathy", "❤️", "共感", 10),
    ("agree", "✅", "賛成", 20),
    ("disagree", "❌", "反対", 30),
    ("insight", "💡", "なるほど", 40),
    ("question", "🤔", "疑問", 50),
)


def init_reactions_db(connect):
    """Create additive tables; do not modify existing posts."""
    with closing(connect()) as con:
        with con:
            con.execute("""CREATE TABLE IF NOT EXISTS reaction_types (
                id TEXT PRIMARY KEY,
                emoji TEXT NOT NULL,
                label TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS reactions (
                message_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                reaction_type_id TEXT NOT NULL,
                PRIMARY KEY (message_id, client_id, reaction_type_id),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                FOREIGN KEY (reaction_type_id) REFERENCES reaction_types(id)
            )""")
            con.executemany(
                "INSERT OR IGNORE INTO reaction_types(id,emoji,label,display_order) VALUES (?,?,?,?)",
                DEFAULT_REACTIONS,
            )


def valid_client_id(value):
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def counts_for(con, message_id):
    rows = con.execute("""
        SELECT r.reaction_type_id AS type_id, COUNT(*) AS total
        FROM reactions r
        JOIN reaction_types t ON t.id = r.reaction_type_id
        WHERE r.message_id = ? AND t.enabled = 1
        GROUP BY r.reaction_type_id
    """, (message_id,)).fetchall()
    return {row["type_id"]: row["total"] for row in rows}


def mine_for(con, message_id, client_id):
    rows = con.execute("""
        SELECT r.reaction_type_id AS type_id
        FROM reactions r
        JOIN reaction_types t ON t.id = r.reaction_type_id
        WHERE r.message_id = ? AND r.client_id = ? AND t.enabled = 1
    """, (message_id, client_id)).fetchall()
    return [row["type_id"] for row in rows]


def create_reactions_blueprint(connect):
    bp = Blueprint("reactions", __name__)

    @bp.get("/api/reactions")
    def get_reactions():
        client_id = request.args.get("client_id", "")
        if not valid_client_id(client_id):
            return jsonify({"error": "valid client_id is required"}), 400

        with closing(connect()) as con:
            types = con.execute("""
                SELECT id, emoji, label
                FROM reaction_types
                WHERE enabled = 1
                ORDER BY display_order, id
            """).fetchall()
            totals = con.execute("""
                SELECT r.message_id, r.reaction_type_id, COUNT(*) AS total
                FROM reactions r
                JOIN reaction_types t ON t.id = r.reaction_type_id
                WHERE t.enabled = 1
                GROUP BY r.message_id, r.reaction_type_id
            """).fetchall()
            mine = con.execute("""
                SELECT r.message_id, r.reaction_type_id
                FROM reactions r
                JOIN reaction_types t ON t.id = r.reaction_type_id
                WHERE r.client_id = ? AND t.enabled = 1
            """, (client_id,)).fetchall()

        by_message = {}
        for row in totals:
            bucket = by_message.setdefault(
                str(row["message_id"]), {"counts": {}, "mine": []}
            )
            bucket["counts"][row["reaction_type_id"]] = row["total"]

        for row in mine:
            bucket = by_message.setdefault(
                str(row["message_id"]), {"counts": {}, "mine": []}
            )
            bucket["mine"].append(row["reaction_type_id"])

        return jsonify({
            "types": [dict(row) for row in types],
            "by_message": by_message
        })

    @bp.post("/api/reactions")
    def toggle_reaction():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "JSON object is required"}), 400

        message_id = data.get("message_id")
        reaction_type_id = data.get("reaction_type_id")
        client_id = data.get("client_id")

        if type(message_id) is not int or message_id < 1:
            return jsonify({
                "error": "positive integer message_id is required"
            }), 400

        if not valid_client_id(client_id):
            return jsonify({"error": "valid client_id is required"}), 400

        if not isinstance(reaction_type_id, str):
            return jsonify({"error": "valid reaction_type_id is required"}), 400

        with closing(connect()) as con:
            with con:
                # Serialize toggles from multiple requests against SQLite.
                con.execute("BEGIN IMMEDIATE")

                columns = {
                    row["name"]
                    for row in con.execute("PRAGMA table_info(messages)")
                }

                parent_column = next(
                    (c for c in (
                        "parent_id",
                        "parent_message_id",
                        "reply_to_id"
                    ) if c in columns),
                    None
                )

                column_sql = f", {parent_column}" if parent_column else ""

                msg = con.execute(
                    f"SELECT id{column_sql} FROM messages WHERE id=?",
                    (message_id,)
                ).fetchone()

                if msg is None:
                    return jsonify({"error": "message not found"}), 404

                if parent_column and msg[parent_column] is not None:
                    return jsonify({
                        "error": "reactions to replies are not supported"
                    }), 400

                kind = con.execute(
                    "SELECT id FROM reaction_types WHERE id=? AND enabled=1",
                    (reaction_type_id,)
                ).fetchone()

                if kind is None:
                    return jsonify({"error": "reaction type not found"}), 404

                already = con.execute("""
                    SELECT 1 FROM reactions
                    WHERE message_id=? AND client_id=? AND reaction_type_id=?
                """, (
                    message_id,
                    client_id,
                    reaction_type_id
                )).fetchone()

                if already:
                    con.execute("""
                        DELETE FROM reactions
                        WHERE message_id=? AND client_id=? AND reaction_type_id=?
                    """, (
                        message_id,
                        client_id,
                        reaction_type_id
                    ))
                    action = "removed"

                else:
                    # Agree and disagree are mutually exclusive.
                    if reaction_type_id in ("agree", "disagree"):
                        opposite = (
                            "disagree"
                            if reaction_type_id == "agree"
                            else "agree"
                        )

                        con.execute("""
                            DELETE FROM reactions
                            WHERE message_id=? AND client_id=? AND reaction_type_id=?
                        """, (
                            message_id,
                            client_id,
                            opposite
                        ))

                    con.execute("""
                        INSERT INTO reactions(
                            message_id,
                            client_id,
                            reaction_type_id
                        )
                        VALUES(?,?,?)
                    """, (
                        message_id,
                        client_id,
                        reaction_type_id
                    ))
                    action = "added"

                counts = counts_for(con, message_id)
                mine = mine_for(con, message_id, client_id)

        return jsonify({
            "message_id": message_id,
            "action": action,
            "counts": counts,
            "mine": mine
        })

    return bp
