"""Start Sinter from an extracted source folder. No pip install required."""
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit("Sinter needs Python 3.10 or newer. Install Python from python.org, then open this launcher again.")

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from sinter.cli import main

if __name__ == "__main__":
    main(sys.argv[1:] or ["serve"])
