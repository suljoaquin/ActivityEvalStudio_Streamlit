"""Shared paths and filesystem bootstrapping for source and frozen builds."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
IS_FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))

# Packaged builds keep mutable configuration and generated reports in the
# user's local app-data folder. Developers can override this with
# ACTIVITY_EVAL_HOME, and a portable copy can set it to a folder next to the exe.
if IS_FROZEN:
    _default_home = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ActivityEvalStudio"
else:
    _default_home = SOURCE_ROOT
HOME_ROOT = Path(os.environ.get("ACTIVITY_EVAL_HOME") or _default_home).expanduser().resolve()

APP_ROOT = HOME_ROOT
CONFIG_DIR = HOME_ROOT / "config"
MAPPINGS_DIR = CONFIG_DIR / "mappings"
TEMPLATES_CONFIG_DIR = CONFIG_DIR / "templates"
PRESETS_DIR = CONFIG_DIR / "presets"
DOCX_DIR = HOME_ROOT / "docx_templates"
SOURCE_DIR = DOCX_DIR / "source"
COMPILED_DIR = DOCX_DIR / "compiled"
DATA_DIR = HOME_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
HISTORY_DIR = DATA_DIR / "history"
CACHE_DIR = DATA_DIR / "cache"

WEB_DIR = BUNDLE_ROOT / "web"
STATIC_DIR = BUNDLE_ROOT / "static"


def seed_home() -> None:
    """Copy bundled configuration into a writable home on first run.

    This is used by frozen builds, Docker/Render-style hosts, and Streamlit
    Cloud, where ACTIVITY_EVAL_HOME points outside the source tree.
    """
    if HOME_ROOT == SOURCE_ROOT:
        return
    HOME_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("config", "docx_templates", "samples"):
        source = BUNDLE_ROOT / name
        target = HOME_ROOT / name
        if source.exists() and not target.exists():
            try:
                shutil.copytree(source, target)
            except FileExistsError:
                pass


def ensure_dirs() -> None:
    for path in (UPLOAD_DIR, HISTORY_DIR, CACHE_DIR, COMPILED_DIR):
        path.mkdir(parents=True, exist_ok=True)
