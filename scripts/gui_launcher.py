"""PyInstaller entry point."""

import multiprocessing

multiprocessing.freeze_support()


def run() -> int:
    from spot2ytmusic.gui import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
