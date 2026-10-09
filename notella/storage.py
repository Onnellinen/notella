"""Transactional local note storage."""

from dataclasses import dataclass
from pathlib import Path
import os
import sqlite3
import uuid


COLORS = {
    "Yellow": "#fff3b0",
    "Pink": "#ffd6e0",
    "Green": "#d8f3dc",
    "Blue": "#d7eaff",
    "Lavender": "#e8dcff",
    "White": "#fafafa",
}


def data_directory() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    if base and Path(base).is_absolute():
        return Path(base) / "notella"
    return Path.home() / ".local" / "share" / "notella"


@dataclass
class Note:
    id: str
    title: str = "Untitled note"
    html: str = ""
    color: str = "Yellow"
    width: int = 420
    height: int = 380
    pin_order: int | None = None


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        os.chmod(path, 0o600)
        self.connection = sqlite3.connect(path)
        try:
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError(f"Unsupported notes database version: {version}")
            self.connection.execute("PRAGMA journal_mode=WAL")
            with self.connection:
                self.connection.execute(
                    """CREATE TABLE IF NOT EXISTS notes (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        html TEXT NOT NULL,
                        color TEXT NOT NULL,
                        width INTEGER NOT NULL,
                        height INTEGER NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                if version < 2:
                    self.connection.execute("ALTER TABLE notes ADD COLUMN pin_order INTEGER")
                self.connection.execute("PRAGMA user_version=2")
        except (sqlite3.Error, OSError, ValueError):
            self.connection.close()
            raise

    def notes(self) -> list[Note]:
        rows = self.connection.execute(
            "SELECT id, title, html, color, width, height, pin_order FROM notes "
            "ORDER BY updated_at DESC, id"
        )
        return [Note(*row) for row in rows]

    def create(self) -> Note:
        note = Note(id=uuid.uuid4().hex)
        self.save(note)
        return note

    def save(self, note: Note) -> None:
        if note.color not in COLORS:
            raise ValueError(f"Unknown note color: {note.color}")
        with self.connection:
            self.connection.execute(
                """INSERT INTO notes
                   (id, title, html, color, width, height, pin_order, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                   ON CONFLICT(id) DO UPDATE SET
                       title=excluded.title, html=excluded.html,
                       color=excluded.color, width=excluded.width,
                       height=excluded.height, pin_order=excluded.pin_order,
                       updated_at=excluded.updated_at""",
                (note.id, note.title, note.html, note.color, note.width, note.height,
                 note.pin_order),
            )

    def delete(self, note_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM notes WHERE id=?", (note_id,))

    def close(self) -> None:
        self.connection.close()
