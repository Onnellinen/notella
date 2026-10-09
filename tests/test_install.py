import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.install import EXTENSION_FILES, FILES, PATH_BLOCK, Installation, desktop_quote, xdg_directory


ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="notella install ")
        base = Path(self.directory.name)
        self.home = base / "home with spaces"
        self.data = base / "data"
        self.config = base / "config"
        self.installation = Installation(self.home, self.data, self.config)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.directory.cleanup()

    def test_install_update_autostart_and_uninstall_preserves_notes(self):
        self.installation.install(ROOT, True)
        for name in FILES:
            self.assertEqual(
                (self.installation.app / name).read_bytes(), (ROOT / name).read_bytes()
            )
        self.assertTrue(os.access(self.installation.launcher, os.X_OK))
        for name in EXTENSION_FILES:
            self.assertEqual(
                (self.installation.extension / name).read_bytes(),
                (ROOT / "gnome-extension" / name).read_bytes(),
            )
        self.assertIn("X-GNOME-Autostart-enabled=true", self.installation.autostart.read_text())
        self.assertIn(
            desktop_quote(str(self.installation.launcher)),
            self.installation.desktop.read_text(),
        )
        database = self.data / "notella" / "notes.sqlite3"
        database.write_bytes(b"saved notes")
        self.installation.install(ROOT, False)
        self.assertFalse(self.installation.autostart.exists())
        self.installation.uninstall()
        self.assertEqual(database.read_bytes(), b"saved notes")
        self.assertFalse(self.installation.launcher.exists())
        self.assertFalse(self.installation.desktop.exists())
        self.assertFalse(self.installation.app.exists())
        self.assertFalse(self.installation.extension.exists())
        self.installation.uninstall()

    def test_launcher_handles_spaces_and_shell_metacharacters(self):
        self.installation = Installation(
            self.home / "special '$`% path", self.data / "special '$`% path", self.config
        )
        self.installation.install(ROOT, False)
        (self.installation.app / "run.py").write_text("print('launcher works')\n")
        result = subprocess.run(
            [str(self.installation.launcher)], capture_output=True, text=True, check=True
        )
        self.assertEqual(result.stdout, "launcher works\n")

    def test_bash_path_launch_reinstall_and_uninstall(self):
        self.home.mkdir(parents=True)
        original = b"# My settings\nexport PERSONAL_SETTING=preserved"
        self.installation.bashrc.write_bytes(original)
        self.installation.bashrc.chmod(0o600)
        for _ in range(2):
            self.installation.install(ROOT, False)
        self.assertEqual(self.installation.bashrc.read_bytes(), original + PATH_BLOCK)
        self.assertEqual(self.installation.bashrc.stat().st_mode & 0o777, 0o600)
        (self.installation.app / "run.py").write_text("print('started by name')\n")
        for path in ("/usr/bin:/bin", f"{self.home}/.local/bin:/usr/bin:/bin"):
            with self.subTest(path=path):
                result = subprocess.run(
                    [
                        "/bin/bash", "--noprofile", "--rcfile",
                        str(self.installation.bashrc), "-ic",
                        'command -v notella; notella; printf "%s\\n" "$PATH" "$PERSONAL_SETTING"',
                    ],
                    env=dict(os.environ, HOME=str(self.home), PATH=path),
                    cwd=self.directory.name,
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [
                    str(self.installation.launcher), "started by name",
                    f"{self.home}/.local/bin:/usr/bin:/bin", "preserved",
                ])
        self.installation.uninstall()
        self.assertEqual(self.installation.bashrc.read_bytes(), original)

    def test_bashrc_symlink_preserved(self):
        self.home.mkdir(parents=True)
        target = self.home / "shell-settings"
        target.write_bytes(b"# User settings\n")
        self.installation.bashrc.symlink_to(target)
        self.installation.install(ROOT, False)
        self.assertTrue(self.installation.bashrc.is_symlink())
        self.assertIn(PATH_BLOCK, target.read_bytes())
        self.installation.uninstall()
        self.assertTrue(self.installation.bashrc.is_symlink())
        self.assertEqual(target.read_bytes(), b"# User settings\n")

    def test_modified_path_block_is_not_overwritten(self):
        self.installation.install(ROOT, False)
        modified = self.installation.bashrc.read_bytes().replace(
            b"case", b"# Custom change\ncase", 1
        )
        self.installation.bashrc.write_bytes(modified)
        with self.assertRaisesRegex(ValueError, "was modified"):
            self.installation.install(ROOT, False)
        with self.assertRaisesRegex(ValueError, "was modified"):
            self.installation.uninstall()
        self.assertEqual(self.installation.bashrc.read_bytes(), modified)
        self.assertTrue(self.installation.launcher.exists())

    @unittest.skipIf(os.geteuid() == 0, "Uninstaller intentionally refuses root")
    def test_standalone_uninstall_preserves_notes_and_is_repeatable(self):
        self.installation.install(ROOT, True)
        database = self.data / "notella" / "notes.sqlite3"
        database.write_bytes(b"saved notes")
        environment = dict(
            os.environ,
            HOME=str(self.home),
            XDG_DATA_HOME=str(self.data),
            XDG_CONFIG_HOME=str(self.config),
        )
        for _ in range(2):
            result = subprocess.run(
                ["/bin/bash", str(ROOT / "uninstall.sh")],
                cwd=self.directory.name,
                env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Uninstalled Notella", result.stdout)
            self.assertEqual(database.read_bytes(), b"saved notes")
            for path in (
                self.installation.app, self.installation.launcher,
                self.installation.desktop, self.installation.autostart,
            ):
                self.assertFalse(path.exists())

    def test_desktop_escaping(self):
        self.assertEqual(desktop_quote("/a path/100%"), '"/a path/100%%"')
        self.assertEqual(desktop_quote('$"`\\'), '"' + '\\\\$\\\\"\\\\`\\\\\\\\' + '"')

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "desktop-file-utils not installed")
    def test_desktop_entries_are_valid(self):
        self.installation.install(ROOT, True)
        for path in (self.installation.desktop, self.installation.autostart):
            subprocess.run(["desktop-file-validate", str(path)], check=True)

    def test_refuses_unmanaged_files(self):
        self.installation.launcher.parent.mkdir(parents=True)
        self.installation.launcher.write_text("my custom program")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            self.installation.install(ROOT, True)
        self.assertEqual(self.installation.launcher.read_text(), "my custom program")

    def test_relative_xdg_ignored_and_absolute_respected(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "relative"}):
            self.assertEqual(xdg_directory("XDG_DATA_HOME", self.data), self.data)
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.data)}):
            self.assertEqual(xdg_directory("XDG_DATA_HOME", self.home), self.data)

    @unittest.skipIf(os.geteuid() == 0, "Installer intentionally refuses root")
    def test_dependency_failures_stop_with_recovery_instructions(self):
        bin_directory = Path(self.directory.name) / "bin"
        bin_directory.mkdir()
        log = Path(self.directory.name) / "apt.log"
        scripts = {
            "dpkg-query": "#!/bin/sh\nexit 1\n",
            "sudo": '#!/bin/sh\nexec "$@"\n',
            "apt-get": (
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$APT_TEST_LOG"\n'
                'if [ "$1" = "$APT_TEST_FAILURE" ]; then\n'
                '  echo "Simulated apt failure" >&2\n  exit 100\nfi\n'
            ),
        }
        for name, script in scripts.items():
            path = bin_directory / name
            path.write_text(script)
            path.chmod(0o755)
        for stage, message, calls in (
            ("update", "Software & Updates > Other Software", 1),
            ("install", "Some system dependencies may already have been installed", 2),
        ):
            with self.subTest(stage=stage):
                log.unlink(missing_ok=True)
                environment = dict(
                    os.environ,
                    PATH=str(bin_directory) + os.pathsep + os.defpath,
                    HOME=str(self.home),
                    XDG_DATA_HOME=str(self.data),
                    XDG_CONFIG_HOME=str(self.config),
                    APT_TEST_LOG=str(log),
                    APT_TEST_FAILURE=stage,
                )
                result = subprocess.run(
                    ["/bin/bash", str(ROOT / "install.sh")],
                    env=environment, capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn("Simulated apt failure", result.stderr)
                self.assertIn("Notella installation stopped", result.stderr)
                self.assertIn(message, result.stderr)
                apt_calls = log.read_text().splitlines()
                self.assertEqual(len(apt_calls), calls)
                self.assertEqual(apt_calls[0], "update --error-on=any")
                if stage == "install":
                    self.assertEqual(
                        apt_calls[1],
                        "install -y python3 python3-pyqt6 qt6-wayland "
                        "gnome-shell-extension-appindicator",
                    )
                self.assertFalse(self.installation.app.exists())
                self.assertFalse(self.installation.launcher.exists())


if __name__ == "__main__":
    unittest.main()
