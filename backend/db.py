import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "husam_prime_ai.sqlite3"
_LOCK = threading.Lock()


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                mode TEXT DEFAULT 'assistant',
                language TEXT DEFAULT 'auto',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                meta TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at)")
        conn.commit()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def create_chat(chat_id: str, title: str, mode: str, language: str, now: str) -> Dict[str, Any]:
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO chats (id, title, mode, language, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, title, mode, language, now, now),
        )
        conn.commit()
    return get_chat(chat_id) or {}


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        return row_to_dict(row) if row else None


def list_chats() -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM chats ORDER BY updated_at DESC").fetchall()
        return [row_to_dict(row) for row in rows]


def update_chat(chat_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    allowed = {"title", "mode", "language", "updated_at"}
    items = [(k, v) for k, v in fields.items() if k in allowed]
    if not items:
        return get_chat(chat_id)
    sql = ", ".join([f"{k}=?" for k, _ in items])
    values = [v for _, v in items] + [chat_id]
    with _LOCK, connect() as conn:
        conn.execute(f"UPDATE chats SET {sql} WHERE id=?", values)
        conn.commit()
    return get_chat(chat_id)


def delete_chat(chat_id: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
        conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        conn.commit()


def add_message(message_id: str, chat_id: str, role: str, content: str, meta: Dict[str, Any], now: str) -> Dict[str, Any]:
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, meta, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (message_id, chat_id, role, content, json.dumps(meta, ensure_ascii=False), now),
        )
        conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_id))
        conn.commit()
    return get_message(message_id) or {}


def get_message(message_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if not row:
            return None
        item = row_to_dict(row)
        try:
            item["meta"] = json.loads(item.get("meta") or "{}")
        except Exception:
            item["meta"] = {}
        return item


def list_messages(chat_id: str, limit: int = 80) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE chat_id=? ORDER BY created_at ASC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        items = []
        for row in rows:
            item = row_to_dict(row)
            try:
                item["meta"] = json.loads(item.get("meta") or "{}")
            except Exception:
                item["meta"] = {}
            items.append(item)
        return items
