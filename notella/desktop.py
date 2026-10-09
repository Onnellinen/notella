"""Session-bus bridge to Notella's GNOME desktop extension."""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage, QDBusServiceWatcher


SERVICE = "org.gnome.Shell.Extensions.Notella"
OBJECT_PATH = "/org/gnome/Shell/Extensions/Notella"
PIN_WIDTH = 340
PIN_HEIGHT = 260


class DesktopBridge(QObject):
    released = pyqtSignal(str, str)
    unavailable = pyqtSignal()

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.bus = QDBusConnection.sessionBus()
        self.watcher = QDBusServiceWatcher(
            SERVICE, self.bus,
            QDBusServiceWatcher.WatchModeFlag.WatchForUnregistration, self,
        )
        self.watcher.serviceUnregistered.connect(lambda name: self.unavailable.emit())
        self.bus.connect(SERVICE, OBJECT_PATH, SERVICE, "Released", self.on_released)

    def available(self) -> bool:
        interface = self.bus.interface()
        return bool(interface and interface.isServiceRegistered(SERVICE).value())

    def call(self, method: str, *arguments) -> None:
        interface = QDBusInterface(SERVICE, OBJECT_PATH, SERVICE, self.bus)
        interface.setTimeout(2000)
        reply = interface.call(method, *arguments)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            if reply.errorName() in (
                "org.freedesktop.DBus.Error.ServiceUnknown",
                "org.freedesktop.DBus.Error.NameHasNoOwner",
                "org.freedesktop.DBus.Error.UnknownObject",
                "org.freedesktop.DBus.Error.UnknownInterface",
            ):
                raise RuntimeError(
                    "The Notella Desktop GNOME extension is not running.\n\n"
                    "After installing Notella, log out of Ubuntu and back in so GNOME "
                    "discovers the extension. Then enable Notella Desktop in Extensions, "
                    "or run:\n"
                    "gnome-extensions enable notella-desktop@notella.local\n\n"
                    "Restart Notella afterward. If GNOME still says the extension does "
                    "not exist, rerun bash install.sh, then log out and back in. "
                    "Pinning requires GNOME Shell 50. Your saved notes are still available.\n\n"
                    f"Desktop service: {reply.errorMessage()}"
                )
            raise RuntimeError(
                "Could not contact the Notella Desktop extension. "
                f"Desktop service: {reply.errorMessage()}"
            )
        values = reply.arguments()
        if len(values) != 1 or not isinstance(values[0], str):
            raise RuntimeError("The Notella desktop extension returned an invalid response.")
        if values[0]:
            raise RuntimeError(values[0])

    def pin(self, note_id: str, order: int) -> None:
        self.call("Pin", note_id, order)

    def unpin(self, note_id: str) -> None:
        self.call("Unpin", note_id)

    @pyqtSlot(str, str)
    def on_released(self, note_id: str, reason: str) -> None:
        self.released.emit(note_id, reason)
