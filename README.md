# Notella

Small, local sticky notes for the Ubuntu desktop. Notella lives in the panel:
create a note, reopen an existing one, or quit from its icon's menu.

- Vibe coded.
- Icon toolbar for bold, italic, underline, bullet lists and numbered lists.
- Six note colors in a clickable swatch palette, editable titles and remembered window sizes.
- Automatic, transactional SQLite saves; no accounts or network services.
- Close a note to hide it without quitting or deleting it.
- Per-user installation and automatic start at desktop login.
- A note-list fallback when the desktop does not provide a tray.
- Desktop-pinned notes with fixed sizes and automatic column layout on GNOME 50.

The initial icon is a simple placeholder. The application source is MIT licensed.

**Current version: 0.2.0.** See the [release notes](CHANGELOG.md) for changes and
upgrade considerations, and the [testing guide](docs/TESTING.md) for verification.

## Quick start

From the downloaded repository:

```sh
bash install.sh
~/.local/bin/notella
```

The panel icon provides **New note**, **Open note** and **Quit Notella**.
In a new Bash terminal, you can use just `notella`.

Normal notes work immediately. **Desktop pinning needs a one-time extension
setup:** log out/in after installation, enable **Notella Desktop** in GNOME
Extensions, then restart Notella. See [Enable desktop pinning](#enable-desktop-pinning-gnome-50).

## Install on Ubuntu

Target: **Ubuntu 26.04 LTS desktop**, including Wayland. Download the repository
ZIP from GitHub and extract it, or clone it. Open a terminal in that folder:

```sh
bash install.sh
```

Run this **as your normal desktop user, not with sudo**. The script prompts for
sudo only if system packages are missing. It installs Ubuntu's `python3`,
`python3-pyqt6`, `qt6-wayland` and `gnome-shell-extension-appindicator` packages
through apt. An Internet connection and administrator privileges are needed for
missing packages. No pip installation or virtual environment is needed.

If apt fails, the installer stops and displays recovery instructions; it does not
disable repositories or bypass package-signature checks. For example, a
third-party PPA that reports `404` or `does not have a Release file` may not
support Ubuntu 26.04 (`resolute`). Disable that specific source in
**Software & Updates > Other Software**, then rerun `bash install.sh`.
Disabling a source does not uninstall its existing software, but stops updates
from that source. For network or signature errors, resolve the reported cause
before retrying. A failed dependency installation may have installed some system
packages, but Notella itself is not installed or updated until dependencies succeed.

Launch **Notella** from Applications, or open a **new Bash terminal** and run:

```sh
notella
```

The installer adds a marked PATH block to `~/.bashrc` for Ubuntu's default Bash
shell. To use the terminal that ran the installer immediately:

```sh
export PATH="$HOME/.local/bin:$PATH"
notella
```

An installer cannot change its parent terminal's environment. The full command
`~/.local/bin/notella` always works without updating PATH. Other shells may need
their own PATH configuration.

The installer does not launch the app automatically. It enables desktop-login
autostart by default. It copies the application, so the downloaded repository can
be moved or removed after installation.

**GNOME panel icon:** Ubuntu normally enables the Ubuntu AppIndicators extension.
If no icon appears, enable **Ubuntu AppIndicators** in the Extensions application
and log out and back in (especially after first installing the extension).
Notella displays a note-list window if Qt reports no tray support, so your notes
remain accessible. If an extension claims tray support but hides the icon,
launch Notella again from Applications to open the note list.

### Enable desktop pinning (GNOME 50)

The installer also copies the **Notella Desktop** GNOME Shell extension.
After the first installation, **log out and back in** so GNOME discovers it,
then enable **Notella Desktop** in the Extensions application, or run:

```sh
gnome-extensions enable notella-desktop@notella.local
```

Restart Notella after enabling the extension. Normal notes work without it;
attempting to pin without the extension displays an explanation.
On Wayland, GNOME Shell integration is needed to place notes precisely and keep
them behind ordinary windows. The extension currently supports **GNOME Shell 50**
(Ubuntu 26.04), not older/newer shell versions. When updating the extension,
log out/in to load the updated code.

If pinning reports that `org.gnome.Shell.Extensions.Notella` was not provided by
any `.service` files, the extension is not running; this is not a missing notes
database or a system service you need to create. Check:

```sh
gnome-extensions info notella-desktop@notella.local
```

If it says the extension does not exist immediately after installing, **log out
of Ubuntu and back in** so the running GNOME Shell discovers the newly copied
extension. Merely closing a terminal or restarting Notella is not enough.
Then run the enable command above and restart Notella. If it is still absent,
rerun the installer and check that you are using GNOME Shell 50.

### Installer options

```sh
bash install.sh --no-autostart   # Do not start at login; also removes existing autostart
bash install.sh --no-deps        # Skip apt; require existing system PyQt6
bash install.sh --uninstall     # Remove app and desktop integration; keep notes
```

To turn autostart back on, rerun it without `--no-autostart`.
Uninstall does not remove shared system packages or terminate a running instance.

### Updating an existing installation

1. Choose **Quit Notella** from its panel menu, not just the note-window close button.
2. [Back up your notes](#data-privacy-and-backups) before upgrading.
3. Download/pull the new source and run `bash install.sh` again. The installer
   refreshes the installed copies without deleting your notes. Include
   `--no-autostart` again if you do not want login startup.
4. Log out/in to load the new GNOME extension code. Enable **Notella Desktop**
   if this is your first pinning-enabled installation.
5. Start Notella from Applications or with `notella`.

Version 0.2.0 upgrades the notes database to schema version 2 when first opened.
This preserves existing notes and adds pin order. Version 0.1.0 cannot open the
upgraded database; downgrading requires restoring a **pre-upgrade backup**.
Simply replacing the program files does not roll back the database.

### Login startup

Installation enables autostart for your user by default; it does **not** start
Notella immediately. At the next desktop login, the panel icon returns and saved
pins are restored when the extension is available. Ordinary notes stay hidden
until opened, except that a note-list window appears when no panel tray is available.
Closing a note is not the same as quitting the application.

### Uninstall

Quit Notella from its panel menu first. If enabled, turn off **Notella Desktop**
in Extensions, then run from the downloaded repository:

```sh
bash uninstall.sh
```

Run as your normal user, without sudo. This removes the application, launcher,
Applications entry, desktop extension and login autostart entry.
**Your saved notes are kept**, so reinstalling restores access to them.
Shared system dependencies are also kept.
Only Notella's marked PATH block is removed from `~/.bashrc`; other shell settings
are preserved. Already-open terminals keep their existing PATH until closed.
The script uses the same uninstall logic as `bash install.sh --uninstall` and
does not run apt or require PyQt6.
If you did not disable the extension first, log out/in to unload its in-memory code.

## Using notes

1. Click the panel icon and choose **New note**, or **Open note** and a title.
   Depending on the desktop, right-click may be needed to display the menu.
2. Edit the title at the top and type in the note.
3. Select text and use the **B**, **I** or **U** formatting icons. With no selection,
   the formatting applies to subsequently typed text.
4. Use the bullet-list or numbered-list icons for the current paragraph or
   selected paragraphs.
   Toggle the active list button off to return to ordinary paragraphs.
   Hover over an icon for its label and keyboard shortcut.
5. Click the **colored square** in the toolbar to open a palette of six colored
   squares, then click a new color. The current color is highlighted; the toolbar
   square and note background update immediately and autosave persists the choice.
   Hover over a square for its color name. Use Tab/Shift+Tab or arrow keys to
   navigate, Space/Enter to select, and Escape or an outside click to cancel.
   There is no color dropdown list. Narrow windows may put toolbar items in the
   overflow menu.
6. Close the window to hide it. Reopen it from the icon; it is not deleted.
   **Delete** permanently removes a note only after confirmation.
7. Choose **Quit Notella** from the panel menu or note-list window to exit.

| Shortcut | Action |
| --- | --- |
| Ctrl+B / Ctrl+I / Ctrl+U | Bold / italic / underline |
| Ctrl+Shift+L | Toggle bullet list |
| Ctrl+Shift+N | Toggle numbered list |
| Ctrl+W | Save and hide note |
| Ctrl+Z / Ctrl+Y | Undo / redo (Qt editor defaults) |

Changes save after **350 ms without another edit**, and immediately before hiding
a note or quitting normally. The status says **Saved** only after the transaction
commits. There is no Save button or manual-save shortcut. On a save error it
displays a red warning (hover for details) and **retries automatically every three
seconds**. Further edits trigger the normal autosave delay. A failed save prevents
normal close/quit. Forced termination, power loss or an OS logout that cannot be
delayed can lose pending, unsaved edits.

Starting Notella again opens the note list in the existing process rather than
running another writer. Login startup restores pinned notes; ordinary saved notes
remain hidden until opened. If the extension is not yet ready, Notella waits up
to 30 seconds, then explains the problem and keeps the saved pins for next time.
On Wayland the compositor controls ordinary window placement and may restrict
focus requests; ordinary sizes are remembered, but exact screen positions are not.

Pasted content is plain text; apply rich formatting using the toolbar. Embedded
images, attachments, cloud synchronization and encryption are not supported.

### Pin notes to the desktop

Use the **pin icon at the top right** of a note to pin or unpin it.

- Pinned notes are **340 x 260 logical pixels** (scaled by the display settings).
- They start at the **primary monitor's top-right usable corner**, with 12-pixel
  gaps, fill downward, then start a new column to the left.
- Pinning order is saved independently of edit times. Rapidly pinning several
  notes preserves that order.
- Notes stay behind ordinary application windows and appear on all workspaces.
  They remain application windows, so GNOME may still include them in its
  overview/window switcher; they are not wallpaper images.
- Pinned notes have no draggable title bar and cannot be resized. Text remains
  editable. Unpinning restores the previous ordinary window size.
- Closing a pinned note with its small **X** or Ctrl+W **unpins and hides it**.
  Quitting Notella keeps pins saved and restores them next time.
- Unpinning or deleting a note closes the gap in the desktop layout.
- If no full slot remains, a new pin is refused with a message; notes never
  overlap or spill onto another monitor.
- Changing the monitor layout recomputes positions. If the usable area becomes
  too small, excess notes become ordinary windows and a notification explains why.
- Disabling the extension turns active pins back into ordinary windows and clears
  those pins. After re-enabling it, use the pin buttons to pin them again.

Existing databases are upgraded automatically to store pin order without
changing note text or formatting. After this upgrade, older Notella versions
cannot open the new schema; keep a pre-upgrade backup if you may need to downgrade.

## Data, privacy and backups

Default database:

```text
~/.local/share/notella/notes.sqlite3
```

If an absolute `XDG_DATA_HOME` is set, the location is
`$XDG_DATA_HOME/notella/notes.sqlite3`. Notes are local, unencrypted rich-text HTML
in SQLite. There is no telemetry. The database file is created with owner-only
permissions.

**For a backup, quit Notella first**, then copy the entire `notella` data directory
(including any SQLite `-wal` / `-shm` files). To restore, quit Notella and put the
backup back in the same location. Do not edit the database while the app is running.
A database that cannot be opened is reported, not silently replaced.

Installed files:

| Location | Purpose |
| --- | --- |
| `~/.local/share/notella/app/` | Application source, icon and license |
| `~/.local/bin/notella` | Executable launcher |
| `~/.local/share/applications/notella.desktop` | Applications menu entry |
| `~/.config/autostart/notella.desktop` | Login startup |
| `~/.local/share/gnome-shell/extensions/notella-desktop@notella.local/` | Desktop pinning extension |
| `~/.bashrc` | Managed PATH block for launching by name in Bash |

The data and config paths respect absolute `XDG_DATA_HOME` / `XDG_CONFIG_HOME`.
The launcher remains in `~/.local/bin`; use its full path if it is not on `PATH`.

## Development and verification

With the Ubuntu dependencies installed, run from the repository:

```sh
/usr/bin/python3 -m notella
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n uninstall.sh
gjs -m tests/test_layout.js
```

Alternatively use Python 3.10+ in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m notella
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

The virtual-environment workflow does not install desktop integration or system
Wayland libraries. Use the Ubuntu installer for a normal desktop installation.
In particular, `pip install` does not install or enable the companion GNOME
extension. When developing extension code, rerun the repository installer and
log out/in to refresh GNOME's loaded copy before testing.
Tests use temporary directories and do not touch your real notes or autostart.
See [the testing guide](docs/TESTING.md) for desktop acceptance checks.

### Launching from a Snap-packaged editor

If launching from VS Code's integrated terminal produces a GLib settings-schema
error or a `/snap/core20/.../libpthread.so.0` symbol error, try Ubuntu's Terminal
application or launch the installed Notella from Applications. Snap-packaged
editors can pass incompatible GTK/GIO paths and settings schemas to child
processes. Notella intentionally does not modify your global desktop environment.

## License

Notella's original code and placeholder artwork use the [MIT license](LICENSE).
Dependencies retain their own licenses. **PyQt6 is GPLv3 or commercially
licensed**, and Qt has its own license terms. MIT licensing of this repository
does not relicense these dependencies: anyone distributing a combined application
or binaries must comply with their applicable licenses.
