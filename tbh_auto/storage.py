from __future__ import annotations

import logging
import time

import numpy as np

from .config import match_tolerance, minimum_match, scale_length
from .constants import DEFAULT_CONFIG
from .input import click_if_found, click_match
from .models import Match, Region, ScreenShot, Template
from .vision import wait_for
from .windows import capture_screen, click_at, scroll_at


def slot_has_item(slot_rgb: np.ndarray, grid_config: dict, config: dict, reference: object | None = None) -> bool:
    margin = scale_length(int(grid_config.get("inner_margin", 5)), config, reference)
    if slot_rgb.shape[0] <= margin * 2 or slot_rgb.shape[1] <= margin * 2:
        return False

    inner = slot_rgb[margin:-margin, margin:-margin, :].astype(np.int16)
    if inner.size == 0:
        return False

    bright_fraction = float((inner.max(axis=2) > 90).mean())
    saturation_fraction = float(((inner.max(axis=2) - inner.min(axis=2)) > 35).mean())
    std = float(inner.std())
    logging.info(
        "first bag slot metrics: bright=%.3f saturation=%.3f std=%.1f",
        bright_fraction,
        saturation_fraction,
        std,
    )
    return (
        bright_fraction >= float(grid_config.get("bright_fraction", 0.08))
        or saturation_fraction >= float(grid_config.get("saturation_fraction", 0.08))
        or std >= float(grid_config.get("std_threshold", 18.0))
    )


def first_bag_slot_has_item(screen: ScreenShot, transfer_button: Match, config: dict) -> bool:
    grid = config.get("inventory_grid_from_transfer", DEFAULT_CONFIG["inventory_grid_from_transfer"])
    left = int(transfer_button.center_x + scale_length(int(grid.get("left", 141)), config, transfer_button) - screen.origin_x)
    top = int(transfer_button.center_y + scale_length(int(grid.get("top", -193)), config, transfer_button) - screen.origin_y)
    slot_size = scale_length(int(grid.get("slot_size", 35)), config, transfer_button)

    if left < 0 or top < 0 or left + slot_size > screen.rgb.shape[1] or top + slot_size > screen.rgb.shape[0]:
        logging.warning("first bag slot is outside the captured screen.")
        return False

    slot_rgb = screen.rgb[top : top + slot_size, left : left + slot_size, :]
    return slot_has_item(slot_rgb, grid, config, transfer_button)


def inventory_sort_expected_center(transfer_button: Match, config: dict) -> tuple[int, int]:
    offset = config.get("inventory_sort_offset_from_transfer", DEFAULT_CONFIG["inventory_sort_offset_from_transfer"])
    x = transfer_button.center_x + scale_length(int(offset.get("x", 257)), config, transfer_button)
    y = transfer_button.center_y + scale_length(int(offset.get("y", -55)), config, transfer_button)
    return x, y


def inventory_sort_search_region(transfer_button: Match, config: dict) -> Region:
    x, y = inventory_sort_expected_center(transfer_button, config)
    radius = max(20, scale_length(int(config.get("inventory_sort_search_radius", 70)), config, transfer_button))
    return Region(left=x - radius, top=y - radius, width=radius * 2, height=radius * 2)


def inventory_grid_center_from_transfer(transfer_button: Match, config: dict) -> tuple[int, int]:
    grid = config.get("inventory_grid_from_transfer", DEFAULT_CONFIG["inventory_grid_from_transfer"])
    left = transfer_button.center_x + scale_length(int(grid.get("left", 141)), config, transfer_button)
    top = transfer_button.center_y + scale_length(int(grid.get("top", -193)), config, transfer_button)
    cols = max(1, int(grid.get("cols", 7)))
    rows = max(1, int(grid.get("rows", 3)))
    pitch_x = scale_length(int(grid.get("pitch_x", 40)), config, transfer_button)
    pitch_y = scale_length(int(grid.get("pitch_y", 40)), config, transfer_button)
    slot_size = scale_length(int(grid.get("slot_size", 35)), config, transfer_button)
    x = int(left + (cols - 1) * pitch_x / 2 + slot_size / 2)
    y = int(top + (rows - 1) * pitch_y / 2 + slot_size / 2)
    return x, y


def reset_inventory_scroll_to_top(transfer_button: Match, config: dict) -> None:
    if not bool(config.get("inventory_scroll_reset_enabled", True)):
        return

    x, y = inventory_grid_center_from_transfer(transfer_button, config)
    notches = max(1, int(config.get("inventory_scroll_reset_wheel_notches", 8)))
    logging.info("reset inventory scroll at (%d, %d) notches=%d", x, y, notches)
    for _ in range(notches):
        scroll_at(x, y, 120, 0.03)
    time.sleep(0.15)


def click_inventory_sort(
    templates: dict[str, Template],
    region: Region | None,
    transfer_button: Match,
    config: dict,
    click_delay: float,
) -> None:
    fallback_x, fallback_y = inventory_sort_expected_center(transfer_button, config)
    if bool(config.get("layout_independent_search", True)):
        tolerance = max(match_tolerance(config), int(config.get("inventory_sort_match_tolerance", 120)))
        minimum = min(minimum_match(config), float(config.get("inventory_sort_minimum_match", 0.90)))
        sort_region = inventory_sort_search_region(transfer_button, config)
        sort_match = wait_for(("inventory_sort",), templates, sort_region, tolerance, minimum, timeout_seconds=1.0)
        if sort_match:
            click_match(sort_match, click_delay)
            return

    logging.info("click inventory sort fallback at (%d, %d)", fallback_x, fallback_y)
    click_at(fallback_x, fallback_y, click_delay)


def storage_button_tolerance(config: dict) -> int:
    return max(match_tolerance(config), int(config.get("storage_button_match_tolerance", 80)))


def storage_button_minimum(config: dict) -> float:
    return min(minimum_match(config), float(config.get("storage_button_minimum_match", 0.90)))


def finish_storage_to_bag(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
) -> None:
    tolerance = storage_button_tolerance(config)
    minimum = storage_button_minimum(config)
    click_delay = float(config["click_delay_seconds"])

    if click_if_found("storage", templates, region, tolerance, minimum, click_delay):
        wait_for(("storage_to_bag",), templates, region, tolerance, minimum, timeout_seconds=2.0)

    transfer = wait_for(("storage_to_bag",), templates, region, tolerance, minimum, timeout_seconds=2.0)
    if not transfer:
        logging.warning("storage-to-bag button was not found.")
        return

    page_offsets = config.get("storage_page_offsets_from_transfer", DEFAULT_CONFIG["storage_page_offsets_from_transfer"])
    max_page_attempts = int(config.get("storage_transfer_max_page_attempts", len(page_offsets)))
    attempts: list[dict | None] = [None] + list(page_offsets)[:max_page_attempts]

    for attempt_index, page_offset in enumerate(attempts):
        if page_offset:
            page_x = transfer.center_x + scale_length(int(page_offset.get("x", 0)), config, transfer)
            page_y = transfer.center_y + scale_length(int(page_offset.get("y", 0)), config, transfer)
            logging.info("click storage page for retry at (%d, %d)", page_x, page_y)
            click_at(page_x, page_y, click_delay)
            transfer = wait_for(("storage_to_bag",), templates, region, tolerance, minimum, timeout_seconds=1.5)
            if not transfer:
                logging.warning("storage-to-bag button disappeared after page switch.")
                return

        click_match(transfer, click_delay)
        time.sleep(0.4)
        reset_inventory_scroll_to_top(transfer, config)
        click_inventory_sort(templates, region, transfer, config, click_delay)
        time.sleep(0.2)
        reset_inventory_scroll_to_top(transfer, config)
        time.sleep(0.2)

        screen = capture_screen(region)
        if not first_bag_slot_has_item(screen, transfer, config):
            logging.info("bag first slot is empty after scroll reset and sorting; storage transfer is complete.")
            return

        if attempt_index < len(attempts) - 1:
            logging.info("bag still has items after transfer; trying another storage page.")

    logging.warning("bag still has items after all configured storage pages were tried.")
