"""Frozen executable entry point."""

import multiprocessing

multiprocessing.freeze_support()


def main() -> int:
    from .gui import main as run_gui

    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
