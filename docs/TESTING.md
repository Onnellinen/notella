# Testing Notella

## Automated tests

Run from the repository root. Install application dependencies using the
[README](../README.md); the layout tests also need `gjs`. CI additionally uses
`desktop-file-utils` to validate generated desktop entries.

```sh
sudo apt-get install gjs desktop-file-utils
```

Then run:

```sh
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n uninstall.sh
gjs -m tests/test_layout.js
```

The suite checks database persistence and transactions, rich-text and list
round-trips, autosave, close-to-hide behavior, save failures, note colors,
single-instance activation, icon-only controls, automatic save retries, pin
order/schema migration, fixed sizes, and installer/autostart/uninstall behavior.
Palette tests check actual swatch pixels, selection, autosave, keyboard navigation
and cancellation; service-error tests check the extension recovery instructions.
Offscreen Qt tests exercise real widgets, but do not prove GNOME panel integration.
The GJS layout tests check exact placement, wrapping, full-desktop thresholds and
non-overlap without running GNOME Shell.

### Isolated GNOME 50 integration test

On Ubuntu 26.04 with GNOME Shell 50, GJS and system PyQt6 installed:

```sh
env -i HOME="$HOME" PATH=/usr/bin:/bin XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
  dbus-run-session -- /usr/bin/python3 tests/desktop_smoke.py
```

This starts a headless GNOME compositor with a virtual monitor, private session
bus and temporary data/config directories, and loads a temporary extension copy.
It does not enable extensions or change settings in your running GNOME session.
It checks actual Wayland window frames, stacking behind other windows, workspace
stickiness, pin order, full-desktop rejection, unpin reflow, extension
disable/re-enable recovery and reservation cleanup after the client exits.
An isolated compositor pointer supplies real Wayland input to open the color
palette on a pinned note; the test then selects a swatch.
It repeatedly raises/activates a pinned window to check that it stays below
ordinary windows. The test-only observation and input endpoints are not part of
the installed extension.

The private session may print portal, tray or session-service warnings because
it is not a full desktop login. Check the `PASS` output and exit status; a
traceback or nonzero exit status is a test failure, not an expected warning.

## Ubuntu desktop acceptance checklist

Run these on a real Ubuntu 26.04 desktop. Check Wayland, and X11 if available.

- Install from a directory with spaces using `bash install.sh`. Confirm that
  missing dependencies prompt for sudo, while app files are owned by your user.
- Launch from Applications. Confirm the icon appears and its menu provides New
  note, Open note and Quit Notella.
- Create two notes with different titles. Enter Unicode text, bold, italic,
  underline, bullet lists and numbered lists; assign different colors.
- Wait for Saved. Resize and close both windows. Confirm Notella keeps running
  and both notes can be reopened from the panel.
- Quit and reopen. Confirm contents, formatting, colors, titles and sizes survive.
- Start a second time and confirm that it opens the existing note-list window.
- Confirm icon tooltips and Ctrl+B/I/U, Ctrl+Shift+L/N and Ctrl+W.
- Open the square color picker in ordinary and pinned notes. Select every color
  and check the swatch/background, selected highlight and persisted value.
  Check Tab/Shift+Tab, arrow keys, Space/Enter, Escape and outside-click dismissal.
- Confirm there is no Save button and Ctrl+S does not force a save.
- In a disposable test profile, verify a failed save displays its error and
  retries without a button; the automated suite injects this failure safely.
- Delete one note; check that Cancel preserves it and Yes removes it after restart.
- Enable Notella Desktop after installation and logout/login. Pin several notes
  rapidly. Confirm 340x260 windows at top-right, then downward, then leftward.
- Click/edit a pinned note while another app overlaps it. It must remain behind
  that app. Switch workspaces; pins should remain available.
- Fill the desktop; confirm another pin is refused and remains an ordinary note.
- Unpin and confirm the previous size returns and the other notes close the gap.
- Close a pin; confirm it is unpinned/hidden. Quit with other pins still present.
- Log out and back in. Confirm the panel icon and saved pins return, while ordinary
  notes remain hidden.
- Reduce the primary monitor's usable area; overflow pins must become ordinary
  windows with a notification rather than disappear offscreen.
- Disable Notella Desktop; confirm pins become ordinary editable windows.
- Disable AppIndicators and restart Notella. Confirm the fallback note list
  appears and lets you create, open and quit. Re-enable the extension.
- Reinstall with `--no-autostart`; log out/in and confirm it does not start.
- Quit, uninstall and reinstall. Confirm saved notes survive.
- Upgrade a copy of a 0.1.0 database and confirm all note text, formatting, colors
  and ordinary window sizes survive. Keep the pre-upgrade copy for rollback.

An inaccessible storage directory is reported at startup. Automated tests inject
SQLite write failures and verify that a failed save neither reports Saved nor
allows normal close/quit. Do not deliberately damage your real database to test
failure handling.

## Release checks

The GitHub Actions workflow runs the Python suite and GJS layout tests with
distribution PyQt6 on Ubuntu 24.04. It does not run the GNOME 50 integration test.
This is a compatibility check, not certification of the Ubuntu 26.04 GNOME shell.
Complete the desktop checklist above on the target OS before publishing a release.

### Last verified: 0.2.0 (2026-10-09)

Environment: Ubuntu 26.04, Python 3.14.4, distribution Qt/PyQt 6.10.2, GNOME 50.1.

| Check | Result |
| --- | --- |
| Python unit suite | 41 tests passed |
| GJS layout geometry and capacity thresholds | Passed |
| Isolated GNOME Wayland integration | Passed |
| Installed launcher outside the source tree and single-instance activation | Passed |
| Uninstall preserving notes and removing extension files | Passed |
| Shell syntax and Python compilation | Passed |
| Python 0.2.0 wheel build | Passed |
| Real panel-menu interaction, physical monitor changes and logout/login | Manual checklist still required |

Update this record when running a new release candidate; do not treat it as a
guarantee for untested GNOME versions or desktop configurations.
