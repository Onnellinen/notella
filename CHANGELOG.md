# Changelog

## 0.2.0 - 2026-10-09

### Changed

- Replaced the color dropdown with a square showing the selected color and a
  clickable six-swatch palette. Color names remain available in tooltips and to
  assistive technologies; keyboard navigation and autosave are preserved.
- Replaced formatting labels with icons for bold, italic, underline, bullets and
  numbered lists. Tooltips and formatting shortcuts remain available.
- Removed the Save button and Ctrl+S. Edits autosave after 350 ms of inactivity;
  closing a note or quitting normally flushes pending changes.
- Failed saves now retry automatically every three seconds. Unsaved changes
  remain visible and block normal close/quit.

### Added

- A top-right pin control and companion **Notella Desktop** extension for GNOME 50.
- Fixed 340 x 260 logical-pixel pinned notes behind ordinary application windows,
  visible across workspaces.
- Primary-monitor layout with 12-pixel gaps: top-right, downward, then in columns
  to the left. A full desktop refuses new pins rather than overlapping notes.
- Persistent pin order and restoration at startup. Unpinning restores the previous
  ordinary window size; closing a pinned note unpins and hides it.
- Layout reflow after unpinning and monitor changes. Pins that no longer fit are
  returned to ordinary windows with a notification.
- GNOME extension installation/removal alongside the application.
- Automated coverage for icons, save retries, schema migration, pin order,
  fixed sizes and extension installation, plus GJS layout tests and an isolated
  GNOME 50 Wayland integration test.

### Fixed

- Missing-extension errors now explain that GNOME needs a logout/login to
  discover a newly installed extension, and include the exact enable command.
  Desktop-service timeouts are no longer described as missing extensions.
- Rapidly pinning notes before autosave completes no longer reuses pin-order
  numbers.
- Pinned notes are lowered after GNOME completes raise/focus handling, so they
  remain behind ordinary application windows.
- Disabling/re-enabling the extension safely returns notes to ordinary windows;
  disconnected clients release their reserved desktop slots.

### Upgrade notes

- Quit Notella and back up your notes before rerunning `bash install.sh`.
- Log out/in to load the extension, enable **Notella Desktop** in Extensions,
  then restart Notella. Normal notes do not require this extension.
- The database upgrades to schema version 2 without changing existing note
  content. Version 0.1.0 cannot read it; downgrading requires a pre-upgrade backup.
- Desktop pinning supports GNOME Shell 50. Manual login/autostart, physical
  monitor changes and the panel menu remain part of the release acceptance
  checklist; see [Testing](docs/TESTING.md).

## 0.1.0 - 2026-10-09

Initial implementation:

- Tray menu for creating/opening rich-text notes and quitting.
- Per-note colors, local SQLite storage, autosave and close-to-hide behavior.
- Per-user Ubuntu dependency installation, Applications entry and login autostart.
- Terminal launcher with managed Bash PATH setup.
- Standalone uninstaller that preserves notes, and actionable apt failure messages.
- Single-instance activation, missing-tray fallback, MIT license and CI tests.
