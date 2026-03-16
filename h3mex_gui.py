#!/usr/bin/env python3

import sys


def main() -> None:
    try:
        from src.gui.app import run
    except ModuleNotFoundError as exc:
        if exc.name == "wx":
            print("wxPython is required for the GUI. Install it with: pip install wxPython")
            return
        raise

    filename = sys.argv[1] if len(sys.argv) > 1 else None
    run(filename)


if __name__ == "__main__":
    main()
