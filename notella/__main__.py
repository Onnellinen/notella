import sys


def main() -> int:
    try:
        from .app import run
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("PyQt6"):
            print(
                "Notella requires PyQt6. Run ./install.sh, or install "
                "python3-pyqt6 and qt6-wayland with apt.",
                file=sys.stderr,
            )
            return 1
        raise
    return run()


if __name__ == "__main__":
    sys.exit(main())
