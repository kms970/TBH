from __future__ import annotations

import ctypes
import logging
import re
import time

import numpy as np
from PIL import Image, ImageGrab

from .config import save_config
from .constants import DEFAULT_CONFIG
from .models import Region, ScreenShot
from .state import clear_active_window, get_active_config, get_active_window_handle, set_active_window


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
user32.EnumWindows.restype = ctypes.c_bool
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = ctypes.c_bool
user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.ShowWindow.restype = ctypes.c_bool
user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.restype = ctypes.c_bool
user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
user32.BringWindowToTop.restype = ctypes.c_bool
user32.SetWindowPos.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
user32.SetWindowPos.restype = ctypes.c_bool
user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = ctypes.c_void_p
user32.ScreenToClient.argtypes = [ctypes.c_void_p, ctypes.POINTER(POINT)]
user32.ScreenToClient.restype = ctypes.c_bool
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t]
user32.PostMessageW.restype = ctypes.c_bool
user32.GetWindowDC.argtypes = [ctypes.c_void_p]
user32.GetWindowDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.ReleaseDC.restype = ctypes.c_int
user32.PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
user32.PrintWindow.restype = ctypes.c_bool
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteObject.restype = ctypes.c_bool
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.restype = ctypes.c_bool
gdi32.GetDIBits.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint,
]
gdi32.GetDIBits.restype = ctypes.c_int

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def normalize_window_title(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", value.lower())


def find_window_region_by_title(keyword: str, config: dict | None = None) -> Region | None:
    keyword = keyword.strip().lower()
    normalized_keyword = normalize_window_title(keyword)
    if not keyword:
        clear_active_window()
        return None

    matches: list[tuple[int, int, Region]] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        buffer = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        title = buffer.value.strip()
        normalized_title = normalize_window_title(title)
        if keyword not in title.lower() and normalized_keyword not in normalized_title:
            return True
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width < 100 or height < 100:
            return True
        padding = (config or {}).get("window_region_padding", DEFAULT_CONFIG["window_region_padding"])
        left = int(rect.left) + int(padding.get("left", 0))
        top = int(rect.top) + int(padding.get("top", 0))
        right = int(rect.right) - int(padding.get("right", 0))
        bottom = int(rect.bottom) - int(padding.get("bottom", 0))
        if right - left >= 100 and bottom - top >= 100:
            region = Region(left=left, top=top, width=right - left, height=bottom - top)
            matches.append((region.width * region.height, int(hwnd), region))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    if not matches:
        clear_active_window()
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    hwnd = ctypes.c_void_p(matches[0][1])
    region = matches[0][2]
    set_active_window(int(matches[0][1]), region)
    if bool((config or {}).get("bring_window_to_front", True)):
        user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetWindowPos(hwnd, ctypes.c_void_p(0), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    return region


def relative_region_to_window(region: Region, window_region: Region) -> dict[str, int]:
    return {
        "left": region.left - window_region.left,
        "top": region.top - window_region.top,
        "width": region.width,
        "height": region.height,
    }


def window_relative_region_from_config(window_region: Region, config: dict) -> Region:
    relative = config.get("search_region_from_window")
    if not bool(config.get("search_region_follow_window", True)) or not isinstance(relative, dict):
        return window_region

    try:
        left = window_region.left + int(relative.get("left", 0))
        top = window_region.top + int(relative.get("top", 0))
        width = int(relative.get("width", window_region.width))
        height = int(relative.get("height", window_region.height))
    except (TypeError, ValueError):
        return window_region

    left = max(window_region.left, left)
    top = max(window_region.top, top)
    right = min(window_region.right, left + width)
    bottom = min(window_region.bottom, top + height)
    if right - left < 100 or bottom - top < 100:
        logging.warning("saved follow-window region is outside the current window; using the whole window.")
        return window_region
    return Region(left=left, top=top, width=right - left, height=bottom - top)


def parse_region(raw: str | None, config: dict) -> Region | None:
    if raw:
        parts = [int(part.strip()) for part in raw.split(",")]
        if len(parts) != 4:
            raise ValueError("--region must be left,top,width,height.")
        return Region(parts[0], parts[1], parts[2], parts[3])
    if bool(config.get("auto_follow_window", True)):
        keyword = str(config.get("window_title_keyword", "TaskBarHero"))
        window_region = find_window_region_by_title(keyword, config)
        if window_region:
            region = window_relative_region_from_config(window_region, config)
            logging.info("window auto-follow region: %s", region.to_config())
            return region
        logging.warning("window title was not found for auto-follow: %s", keyword)
    return Region.from_config(config.get("search_region"))


def current_mouse_position() -> tuple[int, int]:
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def calibrate_region(config: dict) -> None:
    print("게임 UI 전체가 들어가는 사각형을 지정합니다.")
    input("1) 마우스를 검색 영역의 왼쪽 위 모서리에 올리고 Enter를 누르세요.")
    left, top = current_mouse_position()
    input("2) 마우스를 검색 영역의 오른쪽 아래 모서리에 올리고 Enter를 누르세요.")
    right, bottom = current_mouse_position()

    region = Region(
        left=min(left, right),
        top=min(top, bottom),
        width=abs(right - left),
        height=abs(bottom - top),
    )
    if region.width < 50 or region.height < 50:
        raise RuntimeError(f"검색 영역이 너무 작습니다: {region}")

    config["search_region"] = region.to_config()
    save_config(config)
    print(f"저장 완료: {region.to_config()}")


def virtual_screen_origin() -> tuple[int, int]:
    return int(user32.GetSystemMetrics(76)), int(user32.GetSystemMetrics(77))


def virtual_screen_region() -> Region:
    return Region(
        left=int(user32.GetSystemMetrics(76)),
        top=int(user32.GetSystemMetrics(77)),
        width=int(user32.GetSystemMetrics(78)),
        height=int(user32.GetSystemMetrics(79)),
    )


def image_is_blank(rgb: np.ndarray) -> bool:
    if rgb.size == 0:
        return True
    return float(rgb.mean()) < 3.0 and float(rgb.std()) < 3.0


def capture_window_with_printwindow(hwnd: int, region: Region) -> Image.Image | None:
    rect = RECT()
    handle = ctypes.c_void_p(int(hwnd))
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        return None

    window_width = int(rect.right - rect.left)
    window_height = int(rect.bottom - rect.top)
    if window_width <= 0 or window_height <= 0:
        return None

    hwnd_dc = user32.GetWindowDC(handle)
    if not hwnd_dc:
        return None

    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, window_width, window_height)
    old_obj = None
    try:
        if not mem_dc or not bitmap:
            return None
        old_obj = gdi32.SelectObject(mem_dc, bitmap)

        rendered = False
        for flag in (0x00000002, 0):
            if user32.PrintWindow(handle, mem_dc, flag):
                rendered = True
                break
        if not rendered:
            return None

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = window_width
        bmi.bmiHeader.biHeight = -window_height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(window_width * window_height * 4)
        copied = gdi32.GetDIBits(mem_dc, bitmap, 0, window_height, buffer, ctypes.byref(bmi), 0)
        if copied <= 0:
            return None

        image = Image.frombuffer(
            "RGBA",
            (window_width, window_height),
            buffer,
            "raw",
            "BGRA",
            0,
            1,
        ).convert("RGB")

        crop_left = max(0, int(region.left - rect.left))
        crop_top = max(0, int(region.top - rect.top))
        crop_right = min(window_width, crop_left + int(region.width))
        crop_bottom = min(window_height, crop_top + int(region.height))
        if crop_right <= crop_left or crop_bottom <= crop_top:
            return image
        return image.crop((crop_left, crop_top, crop_right, crop_bottom))
    finally:
        if old_obj:
            gdi32.SelectObject(mem_dc, old_obj)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(handle, hwnd_dc)


def capture_screen(region: Region | None) -> ScreenShot:
    if region:
        if bool((get_active_config() or DEFAULT_CONFIG).get("prefer_print_window_capture", True)) and get_active_window_handle() is not None:
            window_image = capture_window_with_printwindow(get_active_window_handle(), region)
            if window_image is not None:
                window_rgb = np.asarray(window_image.convert("RGB"), dtype=np.uint8)
                if not image_is_blank(window_rgb):
                    return ScreenShot(image=window_image, rgb=window_rgb, origin_x=region.left, origin_y=region.top)

        try:
            image = ImageGrab.grab(bbox=region.as_bbox(), all_screens=True)
        except TypeError:
            image = ImageGrab.grab(bbox=region.as_bbox())
        origin_x, origin_y = region.left, region.top
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if (
            bool((get_active_config() or DEFAULT_CONFIG).get("print_window_capture_fallback", True))
            and image_is_blank(rgb)
            and get_active_window_handle() is not None
        ):
            fallback = capture_window_with_printwindow(get_active_window_handle(), region)
            if fallback is not None:
                fallback_rgb = np.asarray(fallback.convert("RGB"), dtype=np.uint8)
                if not image_is_blank(fallback_rgb):
                    logging.debug("ImageGrab returned blank; using PrintWindow capture fallback.")
                    return ScreenShot(image=fallback, rgb=fallback_rgb, origin_x=origin_x, origin_y=origin_y)
    else:
        try:
            image = ImageGrab.grab(all_screens=True)
            origin_x, origin_y = virtual_screen_origin()
        except TypeError:
            image = ImageGrab.grab()
            origin_x, origin_y = 0, 0

    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    return ScreenShot(image=image, rgb=rgb, origin_x=origin_x, origin_y=origin_y)


def post_window_click(x: int, y: int, delay_seconds: float) -> bool:
    hwnd = user32.WindowFromPoint(POINT(int(x), int(y)))
    if not hwnd:
        return False

    point = POINT(int(x), int(y))
    if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
        return False

    lparam = (int(point.y) & 0xFFFF) << 16 | (int(point.x) & 0xFFFF)
    user32.PostMessageW(hwnd, 0x0200, 0, lparam)
    time.sleep(0.03)
    down_ok = user32.PostMessageW(hwnd, 0x0201, 0x0001, lparam)
    time.sleep(0.04)
    up_ok = user32.PostMessageW(hwnd, 0x0202, 0, lparam)
    time.sleep(delay_seconds)
    return bool(down_ok and up_ok)


def click_at(x: int, y: int, delay_seconds: float) -> None:
    click_mode = str((get_active_config() or {}).get("click_mode", "cursor"))
    if click_mode == "window_message":
        logging.warning("window-message click is unsupported for this game; using cursor click.")

    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(delay_seconds)


def scroll_at(x: int, y: int, wheel_delta: int, delay_seconds: float = 0.08) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.03)
    user32.mouse_event(0x0800, 0, 0, int(wheel_delta), 0)
    time.sleep(delay_seconds)
