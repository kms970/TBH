from __future__ import annotations

import sys
from pathlib import Path


def external_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", external_app_dir()))
    return Path(__file__).resolve().parent.parent


APP_DIR = external_app_dir()
RESOURCE_DIR = bundled_resource_dir()
CONFIG_PATH = APP_DIR / "config.json"
EXTERNAL_TEMPLATE_DIR = APP_DIR / "templates"
BUNDLED_TEMPLATE_DIR = RESOURCE_DIR / "templates"
TEMPLATE_DIR = EXTERNAL_TEMPLATE_DIR if EXTERNAL_TEMPLATE_DIR.exists() else BUNDLED_TEMPLATE_DIR
LOG_DIR = APP_DIR / "logs"
