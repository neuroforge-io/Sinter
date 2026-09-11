"""PyInstaller entry point; application modules remain in the sinter package."""
import multiprocessing
from sinter.desktop import main

if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
