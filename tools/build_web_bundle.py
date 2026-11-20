"""Create a clean source bundle for a GitHub/Streamlit Cloud upload."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "ActivityEvalStudio_Streamlit.zip"

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "data",
    "dist",
    "output",
    "test-home",
    "test-home2",
    "test-home3",
    "test-package",
}
EXCLUDE_FILES = {
    ".streamlit/secrets.toml",
    "ActivityEvalStudio.spec",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if str(rel).replace("\\", "/") in EXCLUDE_FILES:
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    return True


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    count = 0
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or not included(path):
                continue
            zf.write(path, path.relative_to(ROOT).as_posix())
            count += 1
    print(f"Wrote {OUT} ({count} files, {OUT.stat().st_size / (1024 * 1024):.1f} MB)")


if __name__ == "__main__":
    main()
