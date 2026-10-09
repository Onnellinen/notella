"""Opt-in GNOME 50 integration test; run with dbus-run-session (see docs/TESTING.md)."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
UUID = "notella-desktop@notella.local"
SERVICE = "org.gnome.Shell.Extensions.Notella"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="notella-desktop-test-") as directory:
        home = Path(directory)
        environment = {
            "HOME": directory,
            "PATH": "/usr/bin:/bin",
            "XDG_DATA_HOME": str(home / "data"),
            "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_CACHE_HOME": str(home / "cache"),
            "XDG_RUNTIME_DIR": os.environ["XDG_RUNTIME_DIR"],
            "DBUS_SESSION_BUS_ADDRESS": os.environ["DBUS_SESSION_BUS_ADDRESS"],
            "GSETTINGS_BACKEND": "keyfile",
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "GNOME",
            "LIBGL_ALWAYS_SOFTWARE": "1",
        }
        extension = home / "data/gnome-shell/extensions" / UUID
        shutil.copytree(ROOT / "gnome-extension", extension)
        # Test-only observation endpoint; never installed with the application.
        source = (extension / "extension.js").read_text()
        source = "import Clutter from 'gi://Clutter';\n" + source
        source = source.replace(
            '<method name="Pin">',
            '<method name="Snapshot"><arg type="s" direction="out"/></method>'
            '<method name="Click"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>'
            '<method name="Pin">',
        )
        source = source.replace(
            "    _slots() {",
            """    Click(x, y) {
        this._testClick = [x, y];
        this._testPointer ??= Clutter.get_default_backend().get_default_seat()
            .create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        Main.overview.hide();
        this._testPointer.notify_absolute_motion(GLib.get_monotonic_time(), x, y);
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
            Main.overview.hide();
            this._testPointer.notify_absolute_motion(GLib.get_monotonic_time(), x, y);
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
                const time = GLib.get_monotonic_time();
                this._testPointer.notify_button(time, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
                this._testPointer.notify_button(time, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
                return GLib.SOURCE_REMOVE;
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    Snapshot() {
        const windows = global.display.sort_windows_by_stacking(
            global.get_window_actors().map(actor => actor.meta_window));
        return JSON.stringify({
            overview: Main.overview.visible,
            pointer: global.get_pointer(),
            click: this._testClick,
            slots: this._slots(),
            pins: [...this._pins.values()].map(entry => ({
                id: entry.id,
                frame: entry.window ? (() => {
                    const r = entry.window.get_frame_rect();
                    return {x:r.x, y:r.y, width:r.width, height:r.height};
                })() : null,
                sticky: entry.window?.is_on_all_workspaces(),
                index: windows.indexOf(entry.window),
            })),
            windows: windows.map(window => ({
                title: window.get_title(), index: windows.indexOf(window),
            })),
        });
    }

    _slots() {""",
        )
        (extension / "extension.js").write_text(source)
        for key, value in (
            ("enabled-extensions", f"['{UUID}']"),
            ("disable-user-extensions", "false"),
        ):
            subprocess.run(
                ["gsettings", "set", "org.gnome.shell", key, value],
                env=environment, check=True,
            )
        display = "notella-test-" + home.name
        with (home / "shell.log").open("w+") as log:
            shell = subprocess.Popen(
                ["gnome-shell", "--headless", "--virtual-monitor=1200x900",
                 "--wayland-display=" + display, "--no-x11"],
                env=environment, stdout=log, stderr=log,
            )
            try:
                ready = False
                for _ in range(100):
                    if shell.poll() is not None:
                        break
                    result = subprocess.run(
                        ["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                         "--object-path", "/org/freedesktop/DBus", "--method",
                         "org.freedesktop.DBus.NameHasOwner", SERVICE],
                        env=environment, capture_output=True, text=True, timeout=3,
                    )
                    if "true" in result.stdout:
                        ready = True
                        break
                    time.sleep(0.2)
                if not ready:
                    log.seek(0)
                    raise RuntimeError("Isolated GNOME extension failed to start:\n" + log.read())
                environment.update(
                    WAYLAND_DISPLAY=display, QT_QPA_PLATFORM="wayland", PYTHONPATH=str(ROOT)
                )
                subprocess.run(
                    ["/usr/bin/python3", str(Path(__file__).resolve()), "--client"],
                    env=environment, check=True, timeout=60,
                )
                result = subprocess.run(
                    ["gdbus", "call", "--session", "--dest", SERVICE,
                     "--object-path", "/org/gnome/Shell/Extensions/Notella",
                     "--method", SERVICE + ".Snapshot"],
                    env=environment, capture_output=True, text=True, check=True,
                )
                assert '"pins":[]' in result.stdout, result.stdout
                print("PASS: disconnected clients leave no reserved desktop slots.")
            finally:
                shell.terminate()
                try:
                    shell.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    shell.kill()
                    shell.wait(timeout=10)


def client() -> None:
    from unittest.mock import patch
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QWidget
    from notella.app import Controller
    from notella.storage import Store

    app = QApplication([])
    app.setApplicationName("Notella")
    app.setQuitOnLastWindowClosed(False)
    store = Store(Path(os.environ["HOME"]) / "test.sqlite3")
    controller = Controller(app, store)
    controller.restore_timer.stop()
    failures = []

    def snapshot():
        interface = QDBusInterface(
            SERVICE, "/org/gnome/Shell/Extensions/Notella", SERVICE,
            QDBusConnection.sessionBus(),
        )
        reply = interface.call("Snapshot")
        assert reply.type() != QDBusMessage.MessageType.ErrorMessage, reply.errorMessage()
        return json.loads(reply.arguments()[0])

    def exercise():
        try:
            ordinary = QWidget()
            ordinary.setWindowTitle("Ordinary application")
            ordinary.resize(700, 500)
            ordinary.show()
            for _ in range(4):
                controller.new_note()
                window = list(controller.windows.values())[-1]
                controller.pin_note(window)
                QTest.qWait(250)
            QTest.qWait(1500)
            state = snapshot()
            assert len(state["pins"]) == 4, state
            ordinary_index = next(
                item["index"] for item in state["windows"] if item["title"] == "Ordinary application"
            )
            for index, pin in enumerate(state["pins"]):
                assert pin["frame"] == state["slots"][index], state
                assert pin["sticky"], state
                assert pin["index"] < ordinary_index, state
            assert state["pins"][3]["frame"]["x"] < state["pins"][0]["frame"]["x"], state
            first = next(iter(controller.windows.values()))
            ordinary.hide()
            QTest.qWait(200)
            position = first.color.mapTo(first, first.color.rect().center())
            frame = state["pins"][0]["frame"]
            interface = QDBusInterface(
                SERVICE, "/org/gnome/Shell/Extensions/Notella", SERVICE,
                QDBusConnection.sessionBus(),
            )
            # A Wayland grabbing popup needs a real compositor-issued input serial.
            reply = interface.call("Click", frame["x"] + position.x(), frame["y"] + position.y())
            assert reply.type() != QDBusMessage.MessageType.ErrorMessage, reply.errorMessage()
            QTest.qWait(1200)
            assert first.color.popup.isVisible(), (
                f"Native click should open the color palette; local={position}, state={snapshot()}"
            )
            QTest.mouseClick(first.color.swatches["Pink"], Qt.MouseButton.LeftButton)
            assert first.note.color == "Pink"
            assert not first.color.popup.isVisible()
            assert first.is_pinned
            ordinary.show()
            QTest.qWait(500)
            for _ in range(3):
                first.raise_()
                first.activateWindow()
                QTest.qWait(700)
                state = snapshot()
                ordinary_index = next(
                    item["index"] for item in state["windows"] if item["title"] == "Ordinary application"
                )
                assert state["pins"][0]["index"] < ordinary_index, state
            while len(controller.windows) < len(state["slots"]):
                controller.new_note()
                controller.pin_note(list(controller.windows.values())[-1])
            controller.new_note()
            overflow = list(controller.windows.values())[-1]
            try:
                controller.pin_note(overflow)
                raise AssertionError("Pinning beyond capacity should fail")
            except RuntimeError as error:
                assert "full" in str(error), error
            assert not overflow.is_pinned
            controller.unpin_note(first)
            QTest.qWait(800)
            state = snapshot()
            assert first.note.id not in [pin["id"] for pin in state["pins"]]
            assert state["pins"][0]["frame"] == state["slots"][0], state
            assert controller.save_all()
            with patch.object(controller, "error") as error:
                subprocess.run(["gnome-extensions", "disable", UUID], check=True)
                QTest.qWait(1000)
                assert not any(window.is_pinned for window in controller.windows.values())
                error.assert_called_once()
            subprocess.run(["gnome-extensions", "enable", UUID], check=True)
            QTest.qWait(1000)
            assert controller.desktop.available()
            controller.pin_note(first)
            QTest.qWait(800)
            assert len(snapshot()["pins"]) == 1
            print("PASS: GNOME 50 Wayland placement, 340x260 frames, downward/leftward layout,")
            print("desktop stacking, sticky workspaces, full-desktop rejection, unpin reflow")
            print("native color-palette interaction and extension disable/re-enable recovery.")
        except (AssertionError, RuntimeError, StopIteration) as error:
            failures.append(error)
            traceback.print_exc()
            print(f"FAIL: {error}", file=sys.stderr)
        finally:
            controller.quit()

    QTimer.singleShot(0, exercise)
    app.exec()
    store.close()
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["--client"]:
        client()
    else:
        main()
