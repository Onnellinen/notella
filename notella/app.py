"""Qt user interface and desktop lifecycle."""

import hashlib
from pathlib import Path
import signal
import sqlite3
import sys

from PyQt6.QtCore import QEvent, QLockFile, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QKeyEvent,
    QResizeEvent,
    QTextCharFormat,
    QTextCursor,
    QTextListFormat,
)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .storage import COLORS, Note, Store, data_directory
from .desktop import DesktopBridge, PIN_HEIGHT, PIN_WIDTH
from .icons import toolbar_icon


STORAGE_ERRORS = (sqlite3.Error, OSError, ValueError)


class ColorPicker(QToolButton):
    colorSelected = pyqtSignal(str)

    def __init__(self, color: str):
        super().__init__()
        self.setFixedSize(30, 30)
        self.setIconSize(QSize(24, 24))
        self.popup = QMenu(self)
        self.popup.setAccessibleName("Note color palette")
        grid = QWidget()
        layout = QGridLayout(grid)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.swatches: dict[str, QToolButton] = {}
        for index, (name, value) in enumerate(COLORS.items()):
            swatch = QToolButton()
            swatch.setFixedSize(34, 34)
            swatch.setIconSize(QSize(24, 24))
            swatch.setIcon(toolbar_icon("color", QColor(value)))
            swatch.setToolTip(name)
            swatch.setAccessibleName(name)
            swatch.setCheckable(True)
            swatch.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            swatch.installEventFilter(self)
            swatch.clicked.connect(lambda checked=False, name=name: self.choose_color(name))
            self.swatches[name] = swatch
            layout.addWidget(swatch, index // 3, index % 3)
        action = QWidgetAction(self.popup)
        action.setDefaultWidget(grid)
        self.popup.addAction(action)
        self.set_color(color)
        self.clicked.connect(self.show_palette)

    def set_color(self, color: str) -> None:
        if color not in COLORS:
            raise ValueError(f"Unknown note color: {color}")
        self.selected_color = color
        self.setIcon(toolbar_icon("color", QColor(COLORS[color])))
        self.setToolTip(f"Note color: {color}. Click to change.")
        self.setAccessibleName(f"Note color: {color}")
        for name, swatch in self.swatches.items():
            swatch.setChecked(name == color)

    def show_palette(self) -> None:
        self.popup.popup(self.mapToGlobal(QPoint(0, self.height())))
        self.swatches[self.selected_color].setFocus(Qt.FocusReason.PopupFocusReason)

    def choose_color(self, color: str) -> None:
        changed = color != self.selected_color
        self.set_color(color)
        self.popup.close()
        self.setFocus()
        if changed:
            self.colorSelected.emit(color)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            buttons = list(self.swatches.values())
            if watched in buttons:
                steps = {
                    Qt.Key.Key_Tab: -1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1,
                    Qt.Key.Key_Backtab: -1,
                    Qt.Key.Key_Left: -1,
                    Qt.Key.Key_Right: 1,
                    Qt.Key.Key_Up: -3,
                    Qt.Key.Key_Down: 3,
                }
                if event.key() in steps:
                    index = (buttons.index(watched) + steps[event.key()]) % len(buttons)
                    buttons[index].setFocus(Qt.FocusReason.TabFocusReason)
                    return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    watched.click()
                    return True
        return super().eventFilter(watched, event)


class NoteWindow(QMainWindow):
    def __init__(self, controller: "Controller", note: Note):
        super().__init__()
        self.controller = controller
        self.note = note
        self.dirty = False
        self.is_pinned = False
        self.setMinimumSize(340, 260)
        self.resize(max(340, note.width), max(260, note.height))
        self.setWindowTitle(note.title + " - Notella")
        self.setWindowIcon(controller.icon)

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(350)
        self.save_timer.timeout.connect(self.save)

        body = QWidget()
        layout = QVBoxLayout(body)
        self.title = QLineEdit(note.title)
        self.title.setPlaceholderText("Note title")
        self.title.setAccessibleName("Note title")
        self.title.setMaxLength(200)
        header = QHBoxLayout()
        header.addWidget(self.title, 1)
        self.pin = QToolButton()
        self.pin.setIcon(toolbar_icon("pin", QColor("#202020")))
        self.pin.setToolTip("Pin to desktop")
        self.pin.setAccessibleName("Pin to desktop")
        self.pin.setCheckable(True)
        self.pin.clicked.connect(self.toggle_pin)
        header.addWidget(self.pin)
        self.hide_button = QToolButton()
        self.hide_button.setIcon(toolbar_icon("close", QColor("#202020")))
        self.hide_button.setToolTip("Close and unpin note")
        self.hide_button.setAccessibleName("Close and unpin note")
        self.hide_button.clicked.connect(self.close)
        self.hide_button.setVisible(False)
        header.addWidget(self.hide_button)
        layout.addLayout(header)
        self.editor = QTextEdit()
        self.editor.setAccessibleName("Note text")
        self.editor.setPlaceholderText("Write something...")
        self.editor.setHtml(note.html)
        # Only text and formatting are persisted, not externally referenced images.
        self.editor.setAcceptRichText(False)
        layout.addWidget(self.editor)
        self.status = QLabel("Saved")
        self.status.setAccessibleName("Save status")
        self.status.setWordWrap(True)
        footer = QHBoxLayout()
        footer.addWidget(self.status, 1)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete)
        footer.addWidget(delete)
        layout.addLayout(footer)
        self.setCentralWidget(body)

        toolbar = QToolBar("Formatting")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)
        self.bold = self.format_action(toolbar, "Bold", "Ctrl+B", self.set_bold)
        self.italic = self.format_action(toolbar, "Italic", "Ctrl+I", self.set_italic)
        self.underline = self.format_action(
            toolbar, "Underline", "Ctrl+U", self.set_underline
        )
        toolbar.addSeparator()
        self.bullets = self.format_action(
            toolbar, "Bullets", "Ctrl+Shift+L",
            lambda checked: self.set_list(QTextListFormat.Style.ListDisc, checked),
        )
        self.numbers = self.format_action(
            toolbar, "Numbers", "Ctrl+Shift+N",
            lambda checked: self.set_list(QTextListFormat.Style.ListDecimal, checked),
        )
        group = QActionGroup(self)
        group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        group.addAction(self.bullets)
        group.addAction(self.numbers)
        toolbar.addSeparator()
        self.color = ColorPicker(note.color)
        self.color.colorSelected.connect(self.change_color)
        toolbar.addWidget(self.color)
        close_action = QAction("Hide note", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close)
        self.addAction(close_action)
        self.apply_color()
        self.title.textChanged.connect(self.mark_dirty)
        self.editor.textChanged.connect(self.mark_dirty)
        self.editor.cursorPositionChanged.connect(self.sync_format_actions)
        self.editor.currentCharFormatChanged.connect(self.sync_format_actions)
        self.sync_format_actions()

    def format_action(self, toolbar, title, shortcut, callback) -> QAction:
        action = QAction(title, self)
        action.setIcon(toolbar_icon(title.lower(), self.palette().windowText().color()))
        action.setToolTip(f"{title} ({shortcut})")
        action.setCheckable(True)
        action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        toolbar.addAction(action)
        return action

    def update_window_title(self) -> None:
        suffix = f" [notella:{self.note.id}]" if self.is_pinned else ""
        self.setWindowTitle(self.note.title + " - Notella" + suffix)

    def set_pinned_appearance(self, pinned: bool) -> None:
        self.is_pinned = pinned
        self.pin.setChecked(pinned)
        self.pin.setToolTip("Unpin from desktop" if pinned else "Pin to desktop")
        self.pin.setAccessibleName(self.pin.toolTip())
        self.hide_button.setVisible(pinned)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, pinned)
        self.update_window_title()
        if pinned:
            self.setFixedSize(PIN_WIDTH, PIN_HEIGHT)
        else:
            self.setMaximumSize(16777215, 16777215)
            self.setMinimumSize(340, 260)
            self.resize(self.note.width, self.note.height)
        self.show()

    def toggle_pin(self, checked: bool) -> None:
        try:
            if checked:
                self.controller.pin_note(self)
            else:
                self.controller.unpin_note(self)
        except (RuntimeError, *STORAGE_ERRORS) as error:
            self.pin.setChecked(self.is_pinned)
            self.controller.error("Could not change desktop pin", error)

    def set_bold(self, checked: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal)
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def set_italic(self, checked: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(checked)
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def set_underline(self, checked: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(checked)
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def set_list(self, style: QTextListFormat.Style, checked: bool) -> None:
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        if checked:
            fmt = QTextListFormat()
            fmt.setStyle(style)
            fmt.setIndent(1)
            cursor.createList(fmt)
        else:
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            block = self.editor.document().findBlock(start)
            while block.isValid() and (block.position() < end or block.contains(start)):
                current_list = block.textList()
                if current_list:
                    current_list.remove(block)
                    block_cursor = QTextCursor(block)
                    fmt_block = block.blockFormat()
                    fmt_block.setIndent(0)
                    block_cursor.setBlockFormat(fmt_block)
                block = block.next()
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self.sync_format_actions()

    def sync_format_actions(self) -> None:
        fmt = self.editor.currentCharFormat()
        self.bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self.italic.setChecked(fmt.fontItalic())
        self.underline.setChecked(fmt.fontUnderline())
        current_list = self.editor.textCursor().currentList()
        style = current_list.format().style() if current_list else None
        self.bullets.setChecked(style == QTextListFormat.Style.ListDisc)
        self.numbers.setChecked(style == QTextListFormat.Style.ListDecimal)

    def apply_color(self) -> None:
        color = COLORS[self.note.color]
        self.editor.setStyleSheet(
            f"QTextEdit {{ background-color: {color}; color: #202020; "
            "selection-background-color: #305b91; selection-color: white; }"
        )
        self.centralWidget().setStyleSheet(f"background-color: {color}; color: #202020;")

    def change_color(self, color: str) -> None:
        self.note.color = color
        self.apply_color()
        self.mark_dirty()
        self.editor.setFocus()

    def mark_dirty(self) -> None:
        self.dirty = True
        self.status.setText("Saving...")
        self.status.setStyleSheet("")
        self.save_timer.start(350)

    def save(self) -> bool:
        self.save_timer.stop()
        if not self.dirty:
            return True
        self.note.title = self.title.text().strip() or "Untitled note"
        self.note.html = self.editor.toHtml()
        if not self.is_pinned:
            self.note.width = self.width()
            self.note.height = self.height()
        try:
            self.controller.store.save(self.note)
        except STORAGE_ERRORS as error:
            self.status.setText("Not saved - retrying automatically")
            self.status.setStyleSheet("color: #a00000; font-weight: bold;")
            self.status.setToolTip(str(error))
            print(f"Notella: cannot save note {self.note.id}: {error}", file=sys.stderr)
            self.save_timer.start(3000)
            return False
        self.dirty = False
        self.status.setText("Saved")
        self.status.setStyleSheet("")
        self.status.setToolTip("")
        self.update_window_title()
        self.controller.refresh()
        return True

    def delete(self) -> None:
        answer = QMessageBox.question(
            self, "Delete note?",
            "Permanently delete this note? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.is_pinned:
                self.controller.unpin_note(self)
            self.controller.store.delete(self.note.id)
        except (RuntimeError, *STORAGE_ERRORS) as error:
            self.controller.error("Could not delete note", error)
            return
        self.save_timer.stop()
        self.dirty = False
        del self.controller.windows[self.note.id]
        self.hide()
        self.deleteLater()
        self.controller.refresh()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "save_timer"):
            self.mark_dirty()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.is_pinned and not self.controller.quitting:
            try:
                self.controller.unpin_note(self)
            except RuntimeError as error:
                event.ignore()
                self.controller.error("Could not unpin note", error)
                return
        if not self.save():
            event.ignore()
            QMessageBox.warning(
                self, "Note not saved",
                "The note could not be saved. It will stay open to protect your "
                "changes. Check the save-status tooltip for details and try again.",
            )
            return
        event.accept()


class NotesWindow(QMainWindow):
    def __init__(self, controller: "Controller"):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Notella - Notes")
        self.setWindowIcon(controller.icon)
        self.resize(420, 360)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.list = QListWidget()
        self.list.setAccessibleName("Saved notes")
        self.list.itemActivated.connect(self.open_selected)
        layout.addWidget(self.list)
        buttons = QHBoxLayout()
        for title, callback in (
            ("New note", controller.new_note),
            ("Open", self.open_selected),
            ("Quit Notella", controller.quit),
        ):
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.setCentralWidget(body)

    def open_selected(self) -> None:
        item = self.list.currentItem()
        if item:
            self.controller.open_note(item.data(Qt.ItemDataRole.UserRole))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.quitting or QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
        else:
            event.ignore()
            QMessageBox.information(
                self, "Panel icon unavailable",
                "Keep this window open to access your notes, or choose Quit Notella. "
                "Enable Ubuntu AppIndicators in the GNOME Extensions app, then "
                "log out and back in to restore the panel icon.",
            )


class Controller:
    def __init__(self, app: QApplication, store: Store):
        self.app = app
        self.store = store
        self.quitting = False
        self.windows: dict[str, NoteWindow] = {}
        self.desktop = DesktopBridge(app)
        self.desktop.released.connect(self.pin_released)
        self.desktop.unavailable.connect(self.desktop_unavailable)
        self.restore_attempts = 0
        self.restore_timer = QTimer(app)
        self.restore_timer.setInterval(1000)
        self.restore_timer.timeout.connect(self.restore_pins)
        self.icon = QIcon(str(Path(__file__).parent / "assets" / "notella.svg"))
        self.manager = NotesWindow(self)
        self.tray = QSystemTrayIcon(self.icon, app)
        self.tray.setToolTip("Notella")
        self.menu = QMenu()
        self.menu.addAction("New note", self.new_note)
        self.open_menu = self.menu.addMenu("Open note")
        self.menu.addAction("All notes...", self.show_manager)
        self.menu.addSeparator()
        self.menu.addAction("Quit Notella", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.refresh()
        self.tray.show()
        self.had_tray = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.had_tray:
            self.show_manager()
        self.tray_timer = QTimer(app)
        self.tray_timer.setInterval(3000)
        self.tray_timer.timeout.connect(self.check_tray)
        self.tray_timer.start()
        self.restore_timer.start()

    def error(self, title: str, error: Exception) -> None:
        print(f"Notella: {title}: {error}", file=sys.stderr)
        QMessageBox.critical(self.manager, title, str(error))

    def refresh(self) -> None:
        try:
            notes = self.store.notes()
        except STORAGE_ERRORS as error:
            self.error("Could not read notes", error)
            return
        self.open_menu.clear()
        current = self.manager.list.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.manager.list.clear()
        for note in notes:
            # Ampersands in titles are literal, not menu mnemonic markers.
            action = self.open_menu.addAction(note.title.replace("&", "&&"))
            action.triggered.connect(
                lambda checked=False, note_id=note.id: self.open_note(note_id)
            )
            self.manager.list.addItem(note.title)
            item = self.manager.list.item(self.manager.list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, note.id)
            if note.id == selected:
                self.manager.list.setCurrentItem(item)
        if not notes:
            self.open_menu.addAction("No notes yet").setEnabled(False)

    def new_note(self) -> None:
        try:
            note = self.store.create()
        except STORAGE_ERRORS as error:
            self.error("Could not create note", error)
            return
        self.refresh()
        self.open_note(note.id)

    def pin_note(self, window: NoteWindow) -> None:
        if window.is_pinned:
            return
        if not window.save():
            raise RuntimeError("The note must be saved before it can be pinned.")
        order = window.note.pin_order
        if order is None:
            notes = self.store.notes() + [opened.note for opened in self.windows.values()]
            order = max(
                (note.pin_order for note in notes if note.pin_order is not None),
                default=-1,
            ) + 1
        self.desktop.pin(window.note.id, order)
        window.note.pin_order = order
        window.note.width, window.note.height = window.width(), window.height()
        window.set_pinned_appearance(True)
        window.mark_dirty()

    def unpin_note(self, window: NoteWindow, notify_desktop: bool = True) -> None:
        if notify_desktop:
            self.desktop.unpin(window.note.id)
        window.note.pin_order = None
        window.set_pinned_appearance(False)
        window.mark_dirty()

    def pin_released(self, note_id: str, reason: str) -> None:
        window = self.windows.get(note_id)
        if window and window.is_pinned:
            self.unpin_note(window, notify_desktop=False)
            self.error("Note unpinned", RuntimeError(reason))

    def desktop_unavailable(self) -> None:
        pinned = [window for window in self.windows.values() if window.is_pinned]
        for window in pinned:
            self.unpin_note(window, notify_desktop=False)
        if pinned and not self.quitting:
            self.error(
                "Desktop pinning stopped",
                RuntimeError("The GNOME extension was disabled. Notes are now ordinary windows."),
            )

    def restore_pins(self) -> None:
        try:
            notes = sorted(
                (note for note in self.store.notes() if note.pin_order is not None),
                key=lambda note: note.pin_order,
            )
        except STORAGE_ERRORS as error:
            self.restore_timer.stop()
            self.error("Could not restore desktop notes", error)
            return
        if not notes:
            self.restore_timer.stop()
            return
        if not self.desktop.available():
            self.restore_attempts += 1
            if self.restore_attempts >= 30:
                self.restore_timer.stop()
                self.error(
                    "Desktop notes not restored",
                    RuntimeError(
                        "Enable Notella Desktop in GNOME Extensions and restart Notella. "
                        "Saved pins have been kept; notes can still be opened from the panel."
                    ),
                )
            return
        self.restore_timer.stop()
        for note in notes:
            self.open_note(note.id)
            window = self.windows.get(note.id)
            if window:
                window.toggle_pin(True)

    def open_note(self, note_id: str) -> None:
        if note_id not in self.windows:
            try:
                note = next((n for n in self.store.notes() if n.id == note_id), None)
                if note is None:
                    raise ValueError("This note no longer exists.")
                if note.color not in COLORS:
                    raise ValueError(f"Unknown saved note color: {note.color}")
            except STORAGE_ERRORS as error:
                self.error("Could not open note", error)
                return
            self.windows[note_id] = NoteWindow(self, note)
        window = self.windows[note_id]
        window.showNormal()
        if not window.is_pinned:
            window.raise_()
            window.activateWindow()
        window.editor.setFocus()

    def show_manager(self) -> None:
        self.manager.notice.setText(
            "Open a note, or create a new one. Closing a note keeps it saved."
            if QSystemTrayIcon.isSystemTrayAvailable() else
            "Panel icon unavailable. Enable Ubuntu AppIndicators in GNOME "
            "Extensions and log out/in. You can use your notes here meanwhile."
        )
        self.manager.showNormal()
        self.manager.raise_()
        self.manager.activateWindow()

    def tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.menu.popup(self.tray.geometry().bottomLeft())
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_manager()

    def check_tray(self) -> None:
        available = QSystemTrayIcon.isSystemTrayAvailable()
        if self.had_tray and not available:
            self.show_manager()
        self.had_tray = available

    def save_all(self) -> bool:
        success = True
        for window in list(self.windows.values()):
            if not window.save():
                window.showNormal()
                success = False
        return success

    def quit(self) -> None:
        if not self.save_all():
            QMessageBox.warning(
                self.manager, "Notella is still running",
                "Some notes could not be saved. Resolve the save errors before "
                "quitting. Your unsaved notes are still open.",
            )
            return
        self.quitting = True
        self.restore_timer.stop()
        self.tray.hide()
        self.app.quit()

    def commit_session(self, session) -> None:
        if not self.save_all():
            session.cancel()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Notella")
    app.setDesktopFileName("notella")
    app.setQuitOnLastWindowClosed(False)
    directory = data_directory()
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        QMessageBox.critical(None, "Notella could not start", str(error))
        return 1

    lock = QLockFile(str(directory / "instance.lock"))
    lock.setStaleLockTime(0)
    server_name = "notella-" + hashlib.sha256(str(directory).encode()).hexdigest()[:24]
    if not lock.tryLock(0):
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        if socket.waitForConnected(2000):
            socket.write(b"show\n")
            socket.waitForBytesWritten(2000)
            socket.disconnectFromServer()
            return 0
        QMessageBox.warning(
            None, "Notella is not available",
            "Another instance is starting or the data directory cannot be locked. "
            "Try again shortly and check the directory permissions.",
        )
        return 1

    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(server_name)
    if not server.listen(server_name):
        QMessageBox.critical(None, "Notella could not start", server.errorString())
        lock.unlock()
        return 1
    try:
        store = Store(directory / "notes.sqlite3")
    except STORAGE_ERRORS as error:
        QMessageBox.critical(
            None, "Notella could not open your notes",
            f"{error}\n\nYour existing database has not been replaced.\n{directory}",
        )
        server.close()
        lock.unlock()
        return 1

    controller = Controller(app, store)

    def activate() -> None:
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            connection.disconnected.connect(connection.deleteLater)
            connection.disconnectFromServer()
        controller.show_manager()

    server.newConnection.connect(activate)
    app.commitDataRequest.connect(controller.commit_session)
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(500)
    previous_signals = {
        sig: signal.signal(sig, lambda signum, frame: controller.quit())
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        return app.exec()
    finally:
        for sig, handler in previous_signals.items():
            signal.signal(sig, handler)
        controller.tray.hide()
        server.close()
        store.close()
        lock.unlock()
