from __future__ import annotations

from .models import Region

_ACTIVE_CONFIG: dict | None = None
_ACTIVE_WINDOW_HANDLE: int | None = None
_ACTIVE_WINDOW_REGION: Region | None = None


def set_active_config(config: dict | None) -> None:
    global _ACTIVE_CONFIG
    _ACTIVE_CONFIG = config


def get_active_config() -> dict | None:
    return _ACTIVE_CONFIG


def set_active_window(hwnd: int, region: Region) -> None:
    global _ACTIVE_WINDOW_HANDLE, _ACTIVE_WINDOW_REGION
    _ACTIVE_WINDOW_HANDLE = hwnd
    _ACTIVE_WINDOW_REGION = region


def clear_active_window() -> None:
    global _ACTIVE_WINDOW_HANDLE, _ACTIVE_WINDOW_REGION
    _ACTIVE_WINDOW_HANDLE = None
    _ACTIVE_WINDOW_REGION = None


def get_active_window_handle() -> int | None:
    return _ACTIVE_WINDOW_HANDLE


def get_active_window_region() -> Region | None:
    return _ACTIVE_WINDOW_REGION
