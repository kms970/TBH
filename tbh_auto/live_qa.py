from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import match_tolerance, minimum_match
from .cube import ensure_cube_open, find_auto_fill_button
from .diagnostics import scan_templates
from .models import Match, Region, ScreenShot, Template
from .paths import LOG_DIR
from .state import set_active_config
from .vision import load_templates
from .windows import capture_screen, click_at, find_window_region_by_title, parse_region


BASE_REGION_WIDTH = 954
BASE_REGION_HEIGHT = 852

SETTINGS_BUTTON_TO_PANEL_LEFT = 257
SETTINGS_BUTTON_TO_PANEL_TOP = 16

PANEL_GRAPHICS_TAB = (116, 63)
PANEL_WINDOW_SIZE_DROPDOWN = (271, 143)
PANEL_WINDOW_SIZE_OPTIONS = {
    "1x": (197, 168),
    "1.25x": (197, 191),
    "1.5x": (197, 213),
}
PANEL_UI_LAYOUT_DROPDOWN = (271, 314)
PANEL_UI_LAYOUT_OPTIONS = {
    "auto": (197, 336),
    "left_top": (197, 359),
    "top": (197, 381),
    "right_top": (197, 403),
    "left_bottom": (197, 425),
    "bottom": (197, 448),
    "right_bottom": (197, 470),
}
PANEL_CLOSE_BUTTON = (288, 16)

REQUIRED_SCAN_MATCHES = ("auto_fill",)


@dataclass(frozen=True)
class PanelGeometry:
    left: int
    top: int
    scale: float


@dataclass(frozen=True)
class SettingsButton:
    x: int
    y: int
    scale: float


def refresh_region(config: dict) -> Region:
    find_window_region_by_title(str(config.get("window_title_keyword", "TaskBarHero")), config)
    region = parse_region(None, config)
    if not region:
        raise RuntimeError("window auto-follow region was not found")
    return region


def click_panel(panel: PanelGeometry, point: tuple[int, int], delay: float = 0.2) -> None:
    click_at(
        panel.left + int(round(point[0] * panel.scale)),
        panel.top + int(round(point[1] * panel.scale)),
        delay,
    )


def connected_components(mask: np.ndarray):
    visited = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    ys, xs = np.nonzero(mask)
    for start_y, start_x in zip(ys, xs):
        if visited[start_y, start_x]:
            continue
        stack = [(int(start_y), int(start_x))]
        visited[start_y, start_x] = True
        min_x = max_x = int(start_x)
        min_y = max_y = int(start_y)
        count = 0
        while stack:
            y, x = stack.pop()
            count += 1
            if x < min_x:
                min_x = x
            elif x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            elif y > max_y:
                max_y = y
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        yield min_x, min_y, max_x, max_y, count


def orange_close_button_components(screen: ScreenShot) -> list[tuple[int, int, int, int, int]]:
    rgb = screen.rgb.astype(np.int16)
    red = rgb[:, :, 0]
    green = rgb[:, :, 1]
    blue = rgb[:, :, 2]
    orange = (red > 145) & (green > 35) & (green < 125) & (blue < 90) & (red > green + 55)
    components: list[tuple[int, int, int, int, int]] = []
    for min_x, min_y, max_x, max_y, count in connected_components(orange):
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        if 8 <= width <= 34 and 8 <= height <= 34 and count >= 25:
            components.append((min_x, min_y, max_x, max_y, count))
    return components


def find_settings_button(screen: ScreenShot) -> SettingsButton | None:
    rgb = screen.rgb.astype(np.int16)
    best: SettingsButton | None = None
    best_score = -1.0
    screen_height, screen_width = screen.rgb.shape[:2]
    expected_gear_x = screen_width * 0.61
    ui_scale = max(0.8, min(2.0, screen_width / BASE_REGION_WIDTH))
    for min_x, min_y, max_x, max_y, count in orange_close_button_components(screen):
        close_center_x = (min_x + max_x) / 2
        close_center_y = (min_y + max_y) / 2
        if not (screen_width * 0.45 <= close_center_x <= screen_width * 0.75):
            continue
        if not (screen_height * 0.15 <= close_center_y <= screen_height * 0.45):
            continue

        width = max_x - min_x + 1
        height = max_y - min_y + 1
        scale = ui_scale
        left = max(0, min_x - int(round(45 * scale)))
        right = max(0, min_x - int(round(4 * scale)))
        top = max(0, min_y - int(round(6 * scale)))
        bottom = min(screen.rgb.shape[0], max_y + int(round(7 * scale)))
        if right <= left or bottom <= top:
            continue
        crop = rgb[top:bottom, left:right, :]
        gray = (
            (crop[:, :, 0] > 55)
            & (crop[:, :, 0] < 155)
            & (np.abs(crop[:, :, 0] - crop[:, :, 1]) < 35)
            & (np.abs(crop[:, :, 1] - crop[:, :, 2]) < 35)
        )
        gray_fraction = float(gray.mean())
        if gray_fraction < 0.12:
            continue
        ys, xs = np.nonzero(gray)
        if xs.size == 0:
            continue
        local_gear_x = left + int(round(float(xs.mean())))
        local_gear_y = top + int(round(float(ys.mean())))
        if not (screen_width * 0.45 <= local_gear_x <= screen_width * 0.75):
            continue
        position_score = max(0.0, 1.0 - abs(local_gear_x - expected_gear_x) / max(1.0, screen_width * 0.20))
        gear_x = screen.origin_x + local_gear_x
        gear_y = screen.origin_y + local_gear_y
        score = gray_fraction + count / 1000.0 + position_score
        if score > best_score:
            best_score = score
            best = SettingsButton(gear_x, gear_y, scale)
    return best


def find_middle_close_button(screen: ScreenShot) -> tuple[int, int] | None:
    candidates = []
    target_x = screen.rgb.shape[1] / 2
    for min_x, min_y, max_x, max_y, count in orange_close_button_components(screen):
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        if center_y > screen.rgb.shape[0] * 0.65:
            continue
        candidates.append((abs(center_x - target_x), center_x, center_y, count))
    if not candidates:
        return None
    _distance, center_x, center_y, _count = min(candidates)
    return int(screen.origin_x + round(center_x)), int(screen.origin_y + round(center_y))


def close_settings_by_region(config: dict) -> None:
    region = refresh_region(config)
    click_at(region.left + int(region.width * 0.639), region.top + int(region.height * 0.279), 0.25)
    time.sleep(0.5)


def ensure_cube_visible(templates: dict[str, Template], config: dict) -> Region:
    region = refresh_region(config)
    ok = ensure_cube_open(templates, region, match_tolerance(config), minimum_match(config), float(config["click_delay_seconds"]))
    if not ok:
        raise RuntimeError("cube/combine UI could not be opened for QA")
    return refresh_region(config)


def open_graphics_settings(templates: dict[str, Template], config: dict) -> PanelGeometry:
    region = ensure_cube_visible(templates, config)
    screen = capture_screen(region)
    button = find_settings_button(screen)
    if not button:
        raise RuntimeError("hero settings button was not found")

    logging.info("open game settings at (%d, %d)", button.x, button.y)
    click_at(button.x, button.y, 0.25)
    time.sleep(0.6)
    region = refresh_region(config)
    panel = PanelGeometry(
        left=int(round(button.x - SETTINGS_BUTTON_TO_PANEL_LEFT * button.scale)),
        top=int(round(button.y - SETTINGS_BUTTON_TO_PANEL_TOP * button.scale)),
        scale=button.scale,
    )
    click_panel(panel, PANEL_GRAPHICS_TAB, 0.2)
    time.sleep(0.35)
    return panel


def close_settings(panel: PanelGeometry | None, config: dict) -> None:
    if panel:
        click_panel(panel, PANEL_CLOSE_BUTTON, 0.25)
        time.sleep(0.5)
    else:
        close_settings_by_region(config)


def set_window_size(templates: dict[str, Template], config: dict, size: str) -> None:
    if size not in PANEL_WINDOW_SIZE_OPTIONS:
        raise ValueError(f"unknown window size: {size}")
    before_region = refresh_region(config)
    panel = open_graphics_settings(templates, config)
    click_panel(panel, PANEL_WINDOW_SIZE_DROPDOWN, 0.2)
    time.sleep(0.25)
    click_panel(panel, PANEL_WINDOW_SIZE_OPTIONS[size], 0.25)
    time.sleep(0.5)

    after_region = refresh_region(config)
    resized = (
        abs(after_region.width - before_region.width) > int(config.get("search_region_window_size_tolerance", 8))
        or abs(after_region.height - before_region.height) > int(config.get("search_region_window_size_tolerance", 8))
    )
    if resized:
        confirm_x = after_region.left + int(after_region.width * 0.562)
        confirm_y = after_region.top + int(after_region.height * 0.577)
        logging.info("confirm window size change at (%d, %d)", confirm_x, confirm_y)
        click_at(confirm_x, confirm_y, 0.15)
        time.sleep(0.8)

    close_settings(None if resized else panel, config)


def set_ui_layout(templates: dict[str, Template], config: dict, layout: str) -> None:
    if layout not in PANEL_UI_LAYOUT_OPTIONS:
        raise ValueError(f"unknown UI layout: {layout}")
    panel = open_graphics_settings(templates, config)
    click_panel(panel, PANEL_UI_LAYOUT_DROPDOWN, 0.2)
    time.sleep(0.25)
    click_panel(panel, PANEL_UI_LAYOUT_OPTIONS[layout], 0.25)
    time.sleep(0.7)
    close_settings(panel, config)


def scan_case(templates: dict[str, Template], config: dict, name: str) -> bool:
    region = ensure_cube_visible(templates, config)
    auto_fill: Match | None = find_auto_fill_button(templates, region, config, timeout_seconds=1.2)
    matches = scan_templates(templates, region, config)
    LOG_DIR.mkdir(exist_ok=True)
    scan_path = LOG_DIR / "last_scan.png"
    if scan_path.exists():
        shutil.copyfile(scan_path, LOG_DIR / f"qa_settings_{name}.png")
    required_ok = bool(auto_fill) and all(matches.get(key) is not None for key in REQUIRED_SCAN_MATCHES)
    logging.info("QA %-24s %s", name, "PASS" if required_ok else "FAIL")
    return required_ok


def run_settings_qa(
    config: dict,
    window_sizes: tuple[str, ...] = ("1.25x", "1.5x"),
    layouts: tuple[str, ...] = ("left_top", "top", "right_top", "left_bottom", "bottom", "right_bottom"),
) -> bool:
    set_active_config(config)
    templates = load_templates(config)
    results: list[tuple[str, bool]] = []
    try:
        results.append(("baseline", scan_case(templates, config, "baseline")))
        for size in window_sizes:
            logging.info("QA set window size: %s", size)
            set_window_size(templates, config, size)
            results.append((f"window_size_{size}", scan_case(templates, config, f"window_size_{size.replace('.', '_')}")))

        logging.info("QA restore window size: 1x")
        set_window_size(templates, config, "1x")
        results.append(("window_size_1x_restored", scan_case(templates, config, "window_size_1x_restored")))

        for layout in layouts:
            logging.info("QA set UI layout: %s", layout)
            set_ui_layout(templates, config, layout)
            results.append((f"layout_{layout}", scan_case(templates, config, f"layout_{layout}")))
    finally:
        try:
            logging.info("QA restore UI layout: auto")
            set_ui_layout(templates, config, "auto")
        except Exception:
            logging.exception("failed to restore UI layout to auto")
        try:
            logging.info("QA restore window size: 1x")
            set_window_size(templates, config, "1x")
        except Exception:
            logging.exception("failed to restore window size to 1x")

    print("\nSettings QA summary")
    for name, ok in results:
        print(f"{name:28} {'PASS' if ok else 'FAIL'}")
    return all(ok for _name, ok in results)
