"""Build the dependency-free core with web assets and Apache notices."""
from pathlib import Path
import shutil
import tempfile
import zipapp

ROOT = Path(__file__).resolve().parents[1]


def build(output=None):
    output = Path(output) if output else ROOT / "dist" / "sinter.pyz"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sinter-build-") as temporary:
        stage = Path(temporary)
        shutil.copytree(ROOT / "src" / "sinter", stage / "sinter",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name in ("LICENSE", "NOTICE"):
            shutil.copyfile(ROOT / name, stage / name)
        zipapp.create_archive(stage, output, main="sinter.cli:launch", compressed=True)
    return output


if __name__ == "__main__":
    print(build())
