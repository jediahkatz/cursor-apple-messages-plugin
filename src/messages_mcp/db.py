from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

APPLE_EPOCH_MS = 978_307_200_000

CHAT_DB = Path(os.environ.get("MESSAGES_DB_PATH", Path.home() / "Library" / "Messages" / "chat.db"))


@dataclass
class MessageRow:
    rowid: int
    guid: str
    text: str
    date: datetime
    is_from_me: bool
    handle_id: str | None
    chat_guid: str
    chat_style: int | None
    service: str | None
    has_attachments: bool
    image_path: str | None
    display_name: str | None


def parse_attributed_body(blob: bytes | None) -> str | None:
    if not blob:
        return None
    marker = b"NSString"
    i = blob.find(marker)
    if i < 0:
        return None
    i += len(marker)
    while i < len(blob) and blob[i] != 0x2B:
        i += 1
    if i >= len(blob):
        return None
    i += 1
    if i >= len(blob):
        return None
    b = blob[i]
    i += 1
    if b == 0x81:
        length = blob[i]
        i += 1
    elif b == 0x82:
        length = int.from_bytes(blob[i : i + 2], "little")
        i += 2
    elif b == 0x83:
        length = int.from_bytes(blob[i : i + 3], "little")
        i += 3
    else:
        length = b
    if i + length > len(blob):
        return None
    try:
        return blob[i : i + length].decode("utf-8")
    except UnicodeDecodeError:
        return blob[i : i + length].decode("utf-8", errors="replace")


def apple_date(ns: int | None) -> datetime:
    if not ns:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    return datetime.fromtimestamp(ns / 1e9 + APPLE_EPOCH_MS / 1000, tz=timezone.utc)


class ChatDB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CHAT_DB
        self.conn: sqlite3.Connection | None = None
        self.error: str | None = None
        self._open()

    def _open(self) -> None:
        uri = f"file:{self.path}?mode=ro"
        try:
            self.conn = sqlite3.connect(uri, uri=True, timeout=5)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("SELECT ROWID FROM message LIMIT 1").fetchone()
        except sqlite3.Error as exc:
            if self.conn is not None:
                self.conn.close()
            self.conn = None
            msg = str(exc)
            if "authorization denied" in msg.lower() or "unable to open" in msg.lower():
                self.error = (
                    f"cannot read {self.path}: {msg}. "
                    "Grant Full Disk Access to Cursor (and your terminal) in "
                    "System Settings → Privacy & Security → Full Disk Access, then restart."
                )
            else:
                self.error = f"cannot read {self.path}: {msg}"

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = None

    def require(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError(self.error or f"cannot read {self.path}")
        return self.conn

    def max_rowid(self) -> int:
        row = self.require().execute("SELECT MAX(ROWID) AS max FROM message").fetchone()
        return int(row["max"] or 0)

    def self_handles(self) -> set[str]:
        rows = self.require().execute(
            """
            SELECT DISTINCT account AS addr FROM message
            WHERE is_from_me = 1 AND account IS NOT NULL AND account != ''
            LIMIT 50
            """
        ).fetchall()
        out: set[str] = set()
        for row in rows:
            addr = row["addr"] or ""
            if len(addr) > 2 and addr[1] == ":":
                addr = addr[2:]
            if addr:
                out.add(addr.lower())
        return out

    def _message_text(self, row: sqlite3.Row) -> str:
        text = row["text"]
        if text:
            return text
        body = row["attributedBody"]
        if isinstance(body, memoryview):
            body = body.tobytes()
        parsed = parse_attributed_body(body if isinstance(body, (bytes, bytearray)) else None)
        return parsed or ""

    def _row_from(self, row: sqlite3.Row) -> MessageRow:
        image_path = row["image_path"]
        return MessageRow(
            rowid=int(row["rowid"]),
            guid=row["guid"],
            text=self._message_text(row),
            date=apple_date(row["date"]),
            is_from_me=bool(row["is_from_me"]),
            handle_id=row["handle_id"],
            chat_guid=row["chat_guid"],
            chat_style=row["chat_style"],
            service=row["service"],
            has_attachments=bool(row["cache_has_attachments"]),
            image_path=str(Path(image_path).expanduser()) if image_path else None,
            display_name=row["display_name"] if "display_name" in row.keys() else None,
        )

    _SELECT = """
        SELECT m.ROWID AS rowid, m.guid, m.text, m.attributedBody, m.date, m.is_from_me,
               m.cache_has_attachments, m.service, h.id AS handle_id,
               c.guid AS chat_guid, c.style AS chat_style, c.display_name AS display_name,
               (
                   SELECT a.filename
                   FROM attachment a
                   JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID
                   WHERE maj.message_id = m.ROWID
                     AND a.filename IS NOT NULL
                     AND (a.mime_type IS NULL OR a.mime_type = '' OR a.mime_type LIKE 'image/%')
                   LIMIT 1
               ) AS image_path
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat c ON c.ROWID = cmj.chat_id
        LEFT JOIN handle h ON h.ROWID = m.handle_id
    """

    def poll_after(self, watermark: int) -> list[MessageRow]:
        rows = self.require().execute(
            self._SELECT + " WHERE m.ROWID > ? ORDER BY m.ROWID ASC",
            (watermark,),
        ).fetchall()
        return [self._row_from(r) for r in rows]

    def history(self, chat_guid: str, limit: int) -> list[MessageRow]:
        rows = self.require().execute(
            self._SELECT + " WHERE c.guid = ? ORDER BY m.date DESC LIMIT ?",
            (chat_guid, limit),
        ).fetchall()
        messages = [self._row_from(r) for r in rows]
        messages.reverse()
        return messages

    def chats_for_handle(self, handle: str) -> list[str]:
        rows = self.require().execute(
            """
            SELECT DISTINCT c.guid FROM chat c
            JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
            JOIN handle h ON h.ROWID = chj.handle_id
            WHERE LOWER(h.id) = ?
            """,
            (handle.lower(),),
        ).fetchall()
        return [r["guid"] for r in rows]

    def chat_participants(self, chat_guid: str) -> list[str]:
        rows = self.require().execute(
            """
            SELECT DISTINCT h.id FROM handle h
            JOIN chat_handle_join chj ON chj.handle_id = h.ROWID
            JOIN chat c ON c.ROWID = chj.chat_id
            WHERE c.guid = ?
            """,
            (chat_guid,),
        ).fetchall()
        return [r["id"] for r in rows if r["id"]]

    def list_chats(self, limit: int) -> list[dict[str, object]]:
        rows = self.require().execute(
            """
            SELECT c.guid, c.display_name, c.style,
                   MAX(m.date) AS last_date,
                   GROUP_CONCAT(DISTINCT h.id) AS participants
            FROM chat c
            JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
            JOIN message m ON m.ROWID = cmj.message_id
            LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
            LEFT JOIN handle h ON h.ROWID = chj.handle_id
            GROUP BY c.ROWID
            ORDER BY last_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[dict[str, object]] = []
        for row in rows:
            kind = "group" if row["style"] == 43 else "dm"
            participants = [p for p in (row["participants"] or "").split(",") if p]
            out.append(
                {
                    "chat_id": row["guid"],
                    "kind": kind,
                    "display_name": row["display_name"],
                    "participants": participants,
                    "last_at": apple_date(row["last_date"]).isoformat(),
                }
            )
        return out

    def find_chats_by_name(self, query: str) -> list[dict[str, object]]:
        q = f"%{query.lower()}%"
        rows = self.require().execute(
            """
            SELECT DISTINCT c.guid, c.display_name, c.style, h.id AS handle_id
            FROM chat c
            LEFT JOIN chat_handle_join chj ON chj.chat_id = c.ROWID
            LEFT JOIN handle h ON h.ROWID = chj.handle_id
            WHERE LOWER(IFNULL(c.display_name, '')) LIKE ?
               OR LOWER(IFNULL(h.id, '')) LIKE ?
            LIMIT 25
            """,
            (q, q),
        ).fetchall()
        return [
            {
                "chat_id": r["guid"],
                "display_name": r["display_name"],
                "kind": "group" if r["style"] == 43 else "dm",
                "handle": r["handle_id"],
            }
            for r in rows
        ]
