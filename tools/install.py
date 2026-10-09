"""Per-user installation using only the Python standard library."""

import argparse
import os
from pathlib import Path
import shlex
import sys
import tempfile


MARKER = "# Managed by Notella"
EXTENSION_UUID = "notella-desktop@notella.local"
EXTENSION_FILES = ("metadata.json", "extension.js", "layout.js")
PATH_BLOCK = b"""
# >>> Notella PATH >>>
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
# <<< Notella PATH <<<
"""
FILES = (
    "notella/__init__.py",
    "notella/__main__.py",
    "notella/app.py",
    "notella/storage.py",
    "notella/desktop.py",
    "notella/icons.py",
    "notella/assets/notella.svg",
    "README.md",
    "CHANGELOG.md",
    "docs/TESTING.md",
    "LICENSE",
    *(f"gnome-extension/{name}" for name in EXTENSION_FILES),
)


def xdg_directory(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value) if value and Path(value).is_absolute() else default


def write_atomic(path: Path, content: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def desktop_quote(value: str) -> str:
    value = value.replace("%", "%%")
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    # Desktop values are unescaped once before Exec is parsed into arguments.
    return '"' + value.replace("\\", "\\\\") + '"'


class Installation:
    def __init__(self, home: Path, data: Path, config: Path):
        self.app = data / "notella" / "app"
        self.launcher = home / ".local" / "bin" / "notella"
        self.desktop = data / "applications" / "notella.desktop"
        self.autostart = config / "autostart" / "notella.desktop"
        self.marker = self.app / ".notella-install"
        self.bashrc = home / ".bashrc"
        self.extension = data / "gnome-shell" / "extensions" / EXTENSION_UUID
        for path in (self.app, self.launcher, self.desktop, self.autostart):
            if "\n" in str(path) or "\r" in str(path):
                raise ValueError("Installation paths must not contain line breaks.")

    def check_owned(self) -> None:
        extension_marker = self.extension / ".notella-install"
        if self.extension.is_symlink() or (self.extension.exists() and (
            not extension_marker.is_file() or extension_marker.read_text() != MARKER
        )):
            raise ValueError(f"Not a managed Notella extension: {self.extension}")
        if self.app.is_symlink():
            raise ValueError(f"Refusing to modify a symlink: {self.app}")
        if self.app.exists() and (
            not self.marker.is_file() or self.marker.read_text() != MARKER
        ):
            raise ValueError(f"Not a managed Notella installation: {self.app}")
        for path in (self.launcher, self.desktop, self.autostart):
            if path.is_symlink() or (path.exists() and MARKER not in path.read_text()):
                raise ValueError(f"Refusing to overwrite an unmanaged file: {path}")

    def update_shell_path(self, enabled: bool) -> None:
        # Follow dotfile symlinks without replacing the symlink itself.
        path = self.bashrc.resolve(strict=True) if self.bashrc.is_symlink() else self.bashrc
        original = path.read_bytes() if path.exists() else b""
        content = original.replace(PATH_BLOCK, b"")
        if b"# >>> Notella PATH >>>" in content or b"# <<< Notella PATH <<<" in content:
            raise ValueError(
                f"The Notella PATH block in {path} was modified. "
                "Remove that block manually and rerun the installer."
            )
        if enabled:
            content += PATH_BLOCK
        if content != original:
            mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
            write_atomic(path, content, mode)

    def install(self, source: Path, autostart: bool) -> None:
        self.check_owned()
        # Read everything before modifying the installation, including on upgrades.
        contents = {name: (source / name).read_bytes() for name in FILES}
        self.update_shell_path(True)
        write_atomic(self.marker, MARKER.encode())
        for name, content in contents.items():
            write_atomic(self.app / name, content)
        write_atomic(self.extension / ".notella-install", MARKER.encode())
        for name in EXTENSION_FILES:
            write_atomic(self.extension / name, contents[f"gnome-extension/{name}"])
        write_atomic(self.extension / "LICENSE", contents["LICENSE"])
        write_atomic(
            self.app / "run.py",
            b"from notella.__main__ import main\nraise SystemExit(main())\n",
        )
        launcher = (
            f"#!/bin/sh\n{MARKER}\n"
            f"exec /usr/bin/python3 {shlex.quote(str(self.app / 'run.py'))} \"$@\"\n"
        )
        write_atomic(self.launcher, launcher.encode(), 0o755)
        icon = str(self.app / "notella" / "assets" / "notella.svg").replace("\\", "\\\\")
        desktop = (
            f"{MARKER}\n[Desktop Entry]\nType=Application\nName=Notella\n"
            "Comment=Local rich-text sticky notes\n"
            f"Exec={desktop_quote(str(self.launcher))}\nIcon={icon}\n"
            "Terminal=false\nCategories=Utility;TextEditor;\n"
            "StartupNotify=false\n"
        )
        write_atomic(self.desktop, desktop.encode())
        if autostart:
            write_atomic(
                self.autostart,
                (desktop + "X-GNOME-Autostart-enabled=true\n").encode(),
            )
        else:
            self.autostart.unlink(missing_ok=True)
        print("Installed Notella. Open a new Bash terminal and run: notella")
        print('To use this terminal now, run: export PATH="$HOME/.local/bin:$PATH"')
        print(f"Or launch from Applications or directly:\n{self.launcher}")
        print("Login autostart: " + ("enabled" if autostart else "disabled"))
        print("If there is no panel icon, enable Ubuntu AppIndicators in GNOME")
        print("Extensions, then log out and back in. A note-list fallback is available.")
        print("Quit and reopen Notella if it was running during this installation.")
        print("Desktop pinning: log out/in once, then enable Notella Desktop in Extensions")
        print(f"or run: gnome-extensions enable {EXTENSION_UUID}")
        print("The desktop extension requires GNOME Shell 50. Restart Notella after enabling it.")

    def uninstall(self) -> None:
        self.check_owned()
        self.update_shell_path(False)
        for name in (*EXTENSION_FILES, "LICENSE", ".notella-install"):
            (self.extension / name).unlink(missing_ok=True)
        if self.extension.is_dir() and not any(self.extension.iterdir()):
            self.extension.rmdir()
        for path in (self.launcher, self.desktop, self.autostart):
            path.unlink(missing_ok=True)
        for name in (*FILES, "run.py"):
            (self.app / name).unlink(missing_ok=True)
        # Remove only our bytecode and known empty directories, never note data.
        for directory in (self.app / "notella" / "__pycache__", self.app / "__pycache__"):
            if directory.is_dir() and not directory.is_symlink():
                for file in directory.iterdir():
                    if file.suffix == ".pyc" and not file.is_symlink():
                        file.unlink()
                if not any(directory.iterdir()):
                    directory.rmdir()
        self.marker.unlink(missing_ok=True)
        for directory in (
            self.app / "notella" / "assets", self.app / "notella",
            self.app / "docs", self.app / "gnome-extension", self.app,
        ):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        print("Uninstalled Notella. Saved notes and system dependencies were kept.")
        print("Quit any already-running Notella instance using its Quit menu.")
        print("If Notella Desktop was enabled, log out/in to unload its in-memory extension.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--no-autostart", action="store_true")
    parser.add_argument("--no-deps", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as your normal desktop user, not root.")
    home = Path.home()
    try:
        installation = Installation(
            home,
            xdg_directory("XDG_DATA_HOME", home / ".local" / "share"),
            xdg_directory("XDG_CONFIG_HOME", home / ".config"),
        )
        if args.uninstall:
            installation.uninstall()
        else:
            installation.install(args.source.resolve(), not args.no_autostart)
    except (OSError, ValueError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
