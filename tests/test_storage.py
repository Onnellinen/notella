import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from notella.storage import Store, data_directory


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "notes.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_persist_all_fields_and_delete(self):
        note = self.store.create()
        note.title = "Shopping & ideas \u2615"
        note.html = "<p><b>Milk</b> and <i>bread</i></p><ol><li>First</li></ol>"
        note.color = "Blue"
        note.width, note.height = 550, 600
        note.pin_order = 7
        self.store.save(note)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.notes(), [note])
        self.store.delete(note.id)
        self.assertEqual(self.store.notes(), [])

    def test_save_failure_preserves_previous_transaction(self):
        note = self.store.create()
        self.store.connection.execute(
            "CREATE TRIGGER fail_update BEFORE UPDATE ON notes "
            "BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END"
        )
        note.html = "Unsaved"
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save(note)
        self.assertEqual(self.store.notes()[0].html, "")

    def test_invalid_color_is_reported(self):
        note = self.store.create()
        note.color = "invalid"
        with self.assertRaises(ValueError):
            self.store.save(note)
        self.assertEqual(self.store.notes()[0].color, "Yellow")

    def test_unique_ids_and_owner_only_database(self):
        first, second = self.store.create(), self.store.create()
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        wal = Path(str(self.path) + "-wal")
        self.assertEqual(wal.stat().st_mode & 0o777, 0o600)

    def test_unsupported_schema_is_not_replaced(self):
        self.store.connection.execute("PRAGMA user_version=99")
        with self.assertRaisesRegex(ValueError, "version: 99"):
            Store(self.path)
        self.assertEqual(
            self.store.connection.execute("PRAGMA user_version").fetchone()[0], 99
        )

    def test_version_one_migration_preserves_notes(self):
        path = Path(self.directory.name) / "version-one.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE notes (id TEXT PRIMARY KEY, title TEXT NOT NULL, html TEXT NOT NULL, "
            "color TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL, "
            "updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO notes VALUES ('old', 'Original', '<b>Keep me</b>', 'Pink', 500, 400, '2026')"
        )
        connection.execute("PRAGMA user_version=1")
        connection.commit()
        connection.close()
        store = Store(path)
        try:
            note = store.notes()[0]
            self.assertEqual(note.html, "<b>Keep me</b>")
            self.assertEqual((note.width, note.height), (500, 400))
            self.assertIsNone(note.pin_order)
            note.pin_order = 0
            store.save(note)
            self.assertEqual(store.notes()[0].pin_order, 0)
            self.assertEqual(store.connection.execute("PRAGMA user_version").fetchone()[0], 2)
        finally:
            store.close()

    def test_corrupt_database_is_not_replaced(self):
        path = Path(self.directory.name) / "corrupt.sqlite3"
        content = b"This is not a SQLite database."
        path.write_bytes(content)
        with self.assertRaises(sqlite3.DatabaseError):
            Store(path)
        self.assertEqual(path.read_bytes(), content)

    def test_xdg_paths(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/tmp/notella-tests"}):
            self.assertEqual(data_directory(), Path("/tmp/notella-tests/notella"))
        with patch.dict(os.environ, {"XDG_DATA_HOME": "relative"}):
            self.assertEqual(
                data_directory(), Path.home() / ".local" / "share" / "notella"
            )


if __name__ == "__main__":
    unittest.main()
