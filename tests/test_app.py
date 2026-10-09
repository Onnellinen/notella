import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtGui import QCloseEvent, QFont, QTextCursor, QTextDocument, QTextListFormat
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtDBus import QDBusMessage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox, QMessageBox, QPushButton, QToolBar

from notella.app import Controller
from notella.storage import COLORS, Store


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "notes.sqlite3")
        self.tray_available = patch(
            "notella.app.QSystemTrayIcon.isSystemTrayAvailable", return_value=False
        )
        self.tray_available.start()
        self.controller = Controller(self.app, self.store)
        self.controller.new_note()
        self.window = next(iter(self.controller.windows.values()))
        self.app.processEvents()

    def tearDown(self):
        self.controller.tray_timer.stop()
        self.controller.restore_timer.stop()
        self.controller.desktop.deleteLater()
        self.controller.tray.hide()
        for window in self.controller.windows.values():
            window.save_timer.stop()
            window.hide()
            window.deleteLater()
        self.controller.manager.hide()
        self.controller.manager.deleteLater()
        self.controller.menu.deleteLater()
        self.controller.tray.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tray_available.stop()
        self.store.close()
        self.directory.cleanup()

    def test_autosave_within_half_second_and_reopen(self):
        self.window.title.setText("Groceries & ideas")
        self.window.editor.setPlainText("Milk \u2615")
        self.window.color.swatches["Green"].click()
        QTest.qWait(500)
        note = self.store.notes()[0]
        self.assertEqual(note.title, "Groceries & ideas")
        self.assertEqual(note.color, "Green")
        self.assertIn("Milk", note.html)
        self.assertFalse(self.window.dirty)
        self.assertEqual(self.window.status.text(), "Saved")
        self.assertTrue(self.window.close())
        self.assertFalse(self.window.isVisible())
        self.controller.open_note(note.id)
        self.assertIs(self.controller.windows[note.id], self.window)
        self.assertTrue(self.window.isVisible())
        self.assertEqual(self.window.editor.toPlainText(), "Milk \u2615")
        self.assertEqual(self.controller.open_menu.actions()[0].text(), "Groceries && ideas")

    def test_rich_text_survives_database_and_document_roundtrip(self):
        self.window.editor.setPlainText("Formatted")
        self.window.editor.selectAll()
        self.window.bold.trigger()
        self.window.italic.trigger()
        self.window.underline.trigger()
        self.assertTrue(self.window.save())
        document = QTextDocument()
        document.setHtml(self.store.notes()[0].html)
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor
        )
        fmt = cursor.charFormat()
        self.assertGreaterEqual(fmt.fontWeight(), QFont.Weight.Bold)
        self.assertTrue(fmt.fontItalic())
        self.assertTrue(fmt.fontUnderline())

    def test_color_palette_selection_and_persistence(self):
        picker = self.window.color
        self.assertIsNone(self.window.findChild(QComboBox))
        self.assertEqual(picker.width(), picker.height())
        self.assertEqual(picker.selected_color, "Yellow")
        self.assertEqual(set(picker.swatches), set(COLORS))
        for name in COLORS:
            picker.click()
            self.app.processEvents()
            self.assertTrue(picker.popup.isVisible())
            self.assertTrue(picker.swatches[picker.selected_color].isChecked())
            swatch = picker.swatches[name]
            self.assertEqual(swatch.width(), swatch.height())
            self.assertEqual(swatch.accessibleName(), name)
            QTest.mouseClick(swatch, Qt.MouseButton.LeftButton)
            self.assertFalse(picker.popup.isVisible())
            self.assertEqual(picker.selected_color, name)
            self.assertEqual(self.window.note.color, name)
            self.assertEqual(
                [key for key, button in picker.swatches.items() if button.isChecked()], [name]
            )
            pixel = picker.icon().pixmap(24, 24).toImage().pixelColor(12, 12)
            self.assertEqual(pixel.name(), COLORS[name])
        QTest.qWait(500)
        self.assertEqual(self.store.notes()[0].color, "White")
        self.assertFalse(self.window.dirty)

    def test_color_palette_escape_and_same_color_do_not_change_note(self):
        self.window.save()
        picker = self.window.color
        picker.click()
        self.app.processEvents()
        QTest.keyClick(picker.swatches["Yellow"], Qt.Key.Key_Escape)
        self.assertFalse(picker.popup.isVisible())
        self.assertEqual(picker.selected_color, "Yellow")
        self.assertFalse(self.window.dirty)
        picker.click()
        QTest.keyClick(picker.swatches["Yellow"], Qt.Key.Key_Space)
        self.assertFalse(picker.popup.isVisible())
        self.assertTrue(picker.swatches["Yellow"].isChecked())
        self.assertFalse(self.window.dirty)

    def test_color_palette_keyboard_navigation(self):
        picker = self.window.color
        picker.click()
        self.app.processEvents()
        QTest.keyClick(picker.swatches["Yellow"], Qt.Key.Key_Tab)
        self.assertTrue(picker.swatches["Pink"].hasFocus())
        QTest.keyClick(picker.swatches["Pink"], Qt.Key.Key_Space)
        self.assertEqual(self.window.note.color, "Pink")
        self.assertFalse(picker.popup.isVisible())
        picker.click()
        self.app.processEvents()
        QTest.keyClick(picker.swatches["Pink"], Qt.Key.Key_Down)
        self.assertTrue(picker.swatches["Lavender"].hasFocus())
        QTest.keyClick(picker.swatches["Lavender"], Qt.Key.Key_Return)
        self.assertEqual(self.window.note.color, "Lavender")
        self.assertFalse(picker.popup.isVisible())

    def test_missing_extension_error_explains_discovery_and_enablement(self):
        reply = QDBusMessage.createError(
            "org.freedesktop.DBus.Error.ServiceUnknown",
            "The name org.gnome.Shell.Extensions.Notella was not provided by any .service files",
        )
        with patch("notella.desktop.QDBusInterface") as interface:
            interface.return_value.call.return_value = reply
            with self.assertRaises(RuntimeError) as error:
                self.controller.desktop.pin(self.window.note.id, 0)
        self.assertIn("log out", str(error.exception))
        self.assertIn("gnome-extensions enable notella-desktop@notella.local", str(error.exception))
        self.assertIn("GNOME Shell 50", str(error.exception))

    def test_desktop_timeout_does_not_claim_extension_is_missing(self):
        reply = QDBusMessage.createError("org.freedesktop.DBus.Error.NoReply", "Timed out")
        with patch("notella.desktop.QDBusInterface") as interface:
            interface.return_value.call.return_value = reply
            with self.assertRaisesRegex(RuntimeError, "Could not contact.*Timed out"):
                self.controller.desktop.pin(self.window.note.id, 0)

    def test_bullet_numbered_and_remove_list(self):
        self.window.editor.setPlainText("One\nTwo\nThree")
        self.window.editor.selectAll()
        self.window.bullets.trigger()
        document = self.window.editor.document()
        self.assertEqual(
            document.firstBlock().textList().format().style(),
            QTextListFormat.Style.ListDisc,
        )
        self.assertEqual(document.firstBlock().textList().count(), 3)
        self.window.numbers.trigger()
        self.assertTrue(self.window.save())
        restored = QTextDocument()
        restored.setHtml(self.store.notes()[0].html)
        self.assertEqual(
            restored.firstBlock().textList().format().style(),
            QTextListFormat.Style.ListDecimal,
        )
        self.assertEqual(restored.firstBlock().textList().count(), 3)
        self.window.numbers.trigger()
        block = document.firstBlock()
        while block.isValid():
            self.assertIsNone(block.textList())
            block = block.next()

    def test_close_flushes_without_waiting_for_timer(self):
        self.window.editor.setPlainText("Immediate close")
        self.assertTrue(self.window.close())
        self.assertIn("Immediate close", self.store.notes()[0].html)
        self.assertFalse(self.window.save_timer.isActive())

    def test_failed_save_blocks_close_and_quit_then_retry_succeeds(self):
        self.window.editor.setPlainText("Important unsaved text")
        with (
            patch.object(self.store, "save", side_effect=sqlite3.OperationalError("full")),
            patch("notella.app.QMessageBox.warning") as warning,
            patch.object(self.app, "quit") as quit_app,
        ):
            self.assertFalse(self.window.save())
            self.assertTrue(self.window.dirty)
            self.assertIn("Not saved", self.window.status.text())
            event = QCloseEvent()
            self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.controller.quit()
            quit_app.assert_not_called()
            self.assertEqual(warning.call_count, 2)
        self.assertTrue(self.window.save())
        self.assertFalse(self.window.dirty)
        self.assertIn("Important unsaved text", self.store.notes()[0].html)

    def test_empty_title_and_window_size_are_saved(self):
        self.window.title.setText("  ")
        self.window.resize(650, 510)
        self.app.processEvents()
        self.assertTrue(self.window.save())
        note = self.store.notes()[0]
        self.assertEqual(note.title, "Untitled note")
        self.assertEqual((note.width, note.height), (650, 510))

    def test_delete_cancels_or_removes_note_without_pending_resave(self):
        self.window.editor.setPlainText("Delete me")
        with patch(
            "notella.app.QMessageBox.question", return_value=QMessageBox.StandardButton.No
        ):
            self.window.delete()
        self.assertEqual(len(self.store.notes()), 1)
        with patch(
            "notella.app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes
        ):
            self.window.delete()
        QTest.qWait(500)
        self.assertEqual(self.store.notes(), [])
        self.assertEqual(self.controller.windows, {})

    def test_no_tray_fallback_stays_accessible(self):
        self.assertTrue(self.controller.manager.isVisible())
        with patch("notella.app.QMessageBox.information"):
            self.assertFalse(self.controller.manager.close())
        self.assertTrue(self.controller.manager.isVisible())

    def test_quit_saves_pending_edit(self):
        self.window.editor.setPlainText("Save on quit")
        with patch.object(self.app, "quit") as quit_app:
            self.controller.quit()
        quit_app.assert_called_once()
        self.assertIn("Save on quit", self.store.notes()[0].html)

    def test_icons_and_no_manual_save(self):
        toolbar = self.window.findChild(QToolBar)
        self.assertEqual(toolbar.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)
        for action in (
            self.window.bold, self.window.italic, self.window.underline,
            self.window.bullets, self.window.numbers,
        ):
            self.assertFalse(action.icon().isNull())
            self.assertTrue(action.toolTip())
        self.assertFalse(any(
            "save" in button.text().lower() for button in self.window.findChildren(QPushButton)
        ))
        self.assertFalse(any(action.shortcut().toString() == "Ctrl+S" for action in self.window.actions()))

    def test_failed_save_retries_automatically(self):
        self.window.editor.setPlainText("Retry me")
        with patch.object(self.store, "save", side_effect=sqlite3.OperationalError("full")):
            self.assertFalse(self.window.save())
            self.assertEqual(self.window.save_timer.interval(), 3000)
            self.assertTrue(self.window.save_timer.isActive())
        QTest.qWait(3250)
        self.assertFalse(self.window.dirty)
        self.assertEqual(self.window.status.text(), "Saved")
        self.assertIn("Retry me", self.store.notes()[0].html)

    def test_pin_fixed_size_unpin_and_original_size(self):
        self.window.resize(560, 460)
        with patch.object(self.controller.desktop, "pin") as pin:
            self.window.toggle_pin(True)
            pin.assert_called_once_with(self.window.note.id, 0)
        self.assertTrue(self.window.is_pinned)
        self.assertTrue(self.window.pin.isChecked())
        self.assertEqual((self.window.width(), self.window.height()), (340, 260))
        self.assertEqual(self.window.minimumSize(), self.window.maximumSize())
        self.assertTrue(self.window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(self.window.save())
        note = self.store.notes()[0]
        self.assertEqual((note.width, note.height), (560, 460))
        self.assertEqual(note.pin_order, 0)
        with patch.object(self.controller.desktop, "unpin") as unpin:
            self.window.toggle_pin(False)
            unpin.assert_called_once_with(note.id)
        self.assertFalse(self.window.is_pinned)
        self.assertEqual((self.window.width(), self.window.height()), (560, 460))
        self.assertTrue(self.window.save())
        self.assertIsNone(self.store.notes()[0].pin_order)

    def test_pin_full_or_extension_missing_leaves_note_unchanged(self):
        with (
            patch.object(self.controller.desktop, "pin", side_effect=RuntimeError("Desktop full")),
            patch.object(self.controller, "error") as error,
        ):
            self.window.toggle_pin(True)
            error.assert_called_once()
        self.assertFalse(self.window.is_pinned)
        self.assertFalse(self.window.pin.isChecked())
        self.assertIsNone(self.window.note.pin_order)

    def test_pin_order_persisted_and_close_unpins(self):
        with patch.object(self.controller.desktop, "pin") as pin:
            self.window.toggle_pin(True)
            self.controller.new_note()
            second = next(w for w in self.controller.windows.values() if w is not self.window)
            second.toggle_pin(True)
            self.assertEqual(pin.call_args.args, (second.note.id, 1))
            second.save()
        with patch.object(self.controller.desktop, "unpin"):
            self.assertTrue(self.window.close())
        self.assertFalse(self.window.is_pinned)
        self.assertIsNone(next(n for n in self.store.notes() if n.id == self.window.note.id).pin_order)

    def test_quit_keeps_pins_but_extension_loss_unpins(self):
        with patch.object(self.controller.desktop, "pin"):
            self.window.toggle_pin(True)
        with patch.object(self.app, "quit"):
            self.controller.quit()
        self.assertEqual(self.store.notes()[0].pin_order, 0)
        self.controller.quitting = False
        with patch.object(self.controller, "error") as error:
            self.controller.desktop_unavailable()
            error.assert_called_once()
        self.assertFalse(self.window.is_pinned)
        self.assertIsNone(self.window.note.pin_order)

    def test_restore_pins_in_saved_order(self):
        first = self.store.notes()[0]
        first.pin_order = 2
        self.store.save(first)
        self.window.note.pin_order = 2
        second = self.store.create()
        second.pin_order = 1
        self.store.save(second)
        with (
            patch.object(self.controller.desktop, "available", return_value=True),
            patch.object(self.controller.desktop, "pin") as pin,
        ):
            self.controller.restore_pins()
        self.assertEqual(
            [call.args for call in pin.call_args_list], [(second.id, 1), (first.id, 2)]
        )


class InstanceTests(unittest.TestCase):
    def test_second_process_activates_first_and_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(
                os.environ, XDG_DATA_HOME=directory, QT_QPA_PLATFORM="offscreen"
            )
            command = [sys.executable, "-m", "notella"]
            with tempfile.TemporaryFile(mode="w+") as log:
                process = subprocess.Popen(
                    command, env=environment, stdout=log, stderr=log
                )
                try:
                    name = "notella-" + hashlib.sha256(
                        str(Path(directory) / "notella").encode()
                    ).hexdigest()[:24]
                    ready = False
                    for _ in range(100):
                        if process.poll() is not None:
                            break
                        socket = QLocalSocket()
                        socket.connectToServer(name)
                        if socket.waitForConnected(50):
                            socket.disconnectFromServer()
                            ready = True
                            break
                        time.sleep(0.05)
                    log.seek(0)
                    self.assertTrue(ready, log.read())
                    result = subprocess.run(
                        command, env=environment, capture_output=True, text=True, timeout=10
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIsNone(process.poll())
                    process.terminate()
                    self.assertEqual(process.wait(timeout=10), 0)
                    self.assertFalse((Path(directory) / "notella" / "instance.lock").exists())
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
