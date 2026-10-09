#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage: ./install.sh [--no-autostart] [--no-deps] [--uninstall]' \
        'Installs for the current user. Uses sudo only for Ubuntu dependencies.' \
        'Uninstall keeps all saved notes.'
}

no_deps=false
uninstall=false
for argument in "$@"; do
    case "$argument" in
        --no-deps) no_deps=true ;;
        --uninstall) uninstall=true ;;
        --no-autostart) ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

if [[ "$EUID" -eq 0 ]]; then
    echo 'Run this as your normal desktop user, not with sudo.' >&2
    exit 1
fi

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if ! "$no_deps" && ! "$uninstall"; then
    if ! command -v apt-get >/dev/null || ! command -v dpkg-query >/dev/null; then
        echo 'Automatic dependency installation requires Ubuntu/Debian.' >&2
        echo 'Install Python 3, PyQt6 and Qt Wayland support, then use --no-deps.' >&2
        exit 1
    fi
    packages=(python3 python3-pyqt6 qt6-wayland gnome-shell-extension-appindicator)
    missing=()
    for package in "${packages[@]}"; do
        if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != 'install ok installed' ]]; then
            missing+=("$package")
        fi
    done
    if ((${#missing[@]})); then
        if ! command -v sudo >/dev/null; then
            echo 'sudo is required to install missing system dependencies.' >&2
            exit 1
        fi
        if ! sudo apt-get update --error-on=any; then
            cat >&2 <<'EOF'

Notella installation stopped: apt could not refresh the package lists.
The apt output above identifies the failing repository or connection.

If a third-party PPA reports "404" or "does not have a Release file",
open Software & Updates > Other Software and disable that specific source,
then rerun: bash install.sh
For network or signature errors, fix the reported problem before retrying.

Notella has not changed your software sources or installed the application.
Do not disable apt security checks to work around this error.
EOF
            exit 1
        fi
        if ! sudo apt-get install -y "${missing[@]}"; then
            cat >&2 <<'EOF'

Notella installation stopped: apt could not install the required dependencies.
Review the apt error above, resolve it, then rerun: bash install.sh
Some system dependencies may already have been installed; rerunning is safe.
The Notella application has not been installed or updated.
EOF
            exit 1
        fi
    fi
fi

if [[ ! -x /usr/bin/python3 ]]; then
    echo '/usr/bin/python3 is required.' >&2
    exit 1
fi
if ! "$uninstall"; then
    /usr/bin/python3 -c 'from PyQt6 import QtCore, QtGui, QtWidgets, QtNetwork, QtDBus' || {
        echo 'Qt dependencies are missing. Run ./install.sh without --no-deps.' >&2
        exit 1
    }
fi

exec /usr/bin/python3 "$source_dir/tools/install.py" --source "$source_dir" "$@"
