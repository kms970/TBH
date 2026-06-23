from __future__ import annotations

import logging
import time

import numpy as np
from PIL import Image

from .config import (
    control_match_tolerance,
    control_minimum_match,
    match_tolerance,
    minimum_match,
    scale_length,
    scale_offset,
    screen_scale_factor,
)
from .constants import (
    AUTO_FILL_BUTTON_TEMPLATES,
    CATEGORY_LABELS,
    CATEGORY_OFFSETS_FROM_AUTOFILL,
    CATEGORY_OFFSETS_FROM_DROPDOWN,
    CATEGORY_OPTION_TEMPLATES,
    DEFAULT_CONFIG,
    LEVEL_RANGE_CHOICES,
    LEVEL_RANGE_KEYS,
)
from .input import click_if_found, click_match
from .models import Match, Region, ScreenShot, Template
from .state import get_active_config
from .vision import find, find_template, find_template_in_screen_region, wait_for
from .windows import capture_screen, click_at


def select_auto_fill_category(
    category: str,
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
    click_delay: float,
    config: dict | None = None,
) -> bool:
    option_name = CATEGORY_OPTION_TEMPLATES.get(category)
    if not option_name:
        logging.warning("unknown auto-fill category: %s", category)
        return False
    if config:
        tolerance = max(tolerance, control_match_tolerance(config))
        minimum_match = min(minimum_match, control_minimum_match(config))

    active_config = config or DEFAULT_CONFIG
    auto_fill = find_auto_fill_button(templates, region, active_config, timeout_seconds=1.0)
    if not auto_fill:
        logging.warning("auto-fill button was not found for category selection.")
        return False

    dropdown_x = auto_fill.center_x + scale_length(68, active_config, auto_fill)
    dropdown_y = auto_fill.center_y
    radius = max(14, scale_length(24, active_config, auto_fill))
    dropdown_region = Region(
        left=dropdown_x - radius,
        top=dropdown_y - radius,
        width=radius * 2,
        height=radius * 2,
    )
    screen = capture_screen(region)
    dropdown = find_template_in_screen_region(
        screen,
        templates["auto_fill_dropdown"],
        dropdown_region,
        tolerance,
        minimum_match,
    )
    if dropdown:
        click_match(dropdown, click_delay)
    else:
        logging.info("click auto-fill dropdown by context offset at (%d, %d)", dropdown_x, dropdown_y)
        click_at(dropdown_x, dropdown_y, click_delay)

    time.sleep(0.15)
    option_region = Region(
        left=auto_fill.center_x - scale_length(90, active_config, auto_fill),
        top=auto_fill.center_y + scale_length(10, active_config, auto_fill),
        width=scale_length(180, active_config, auto_fill),
        height=scale_length(90, active_config, auto_fill),
    )
    screen = capture_screen(region)
    option = find_template_in_screen_region(
        screen,
        templates[option_name],
        option_region,
        tolerance,
        minimum_match,
    )
    if not option:
        dx, dy = scale_offset(CATEGORY_OFFSETS_FROM_AUTOFILL[category], active_config, auto_fill)
        logging.info("select auto-fill category by dropdown offset: %s", category)
        click_at(auto_fill.center_x + dx, auto_fill.center_y + dy, click_delay)
        return True

    if not option:
        logging.warning("auto-fill category option was not found: %s", category)
        return False

    logging.info("select auto-fill category: %s", CATEGORY_LABELS.get(category, category))
    click_match(option, click_delay)
    return True


def level_range_button_center(
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
    config: dict | None = None,
) -> tuple[int, int, float] | None:
    level_tolerance = max(tolerance, 90 if screen_scale_factor(config) > 1.0 else tolerance)
    level_minimum = min(minimum_match, 0.95 if screen_scale_factor(config) > 1.0 else minimum_match)

    current = find("level_range_button_20_40", templates, region, level_tolerance, level_minimum)
    if current:
        return current.center_x, current.center_y, current.scale

    sample = find("level_range_button_sample", templates, region, level_tolerance, level_minimum)
    if sample:
        return sample.center_x, sample.center_y, sample.scale

    reference = find("auto_fill_dropdown", templates, region, tolerance, minimum_match)
    if reference:
        dx, dy = scale_offset((82, -224), config, reference)
        return reference.center_x + dx, reference.center_y + dy, reference.scale

    auto_fill = wait_for(
        AUTO_FILL_BUTTON_TEMPLATES,
        templates,
        region,
        tolerance,
        minimum_match,
        timeout_seconds=1.0,
    )
    if auto_fill:
        dx, dy = scale_offset((150, -223), config, auto_fill)
        return auto_fill.center_x + dx, auto_fill.center_y + dy, auto_fill.scale

    return None


def level_range_row_is_locked(
    templates: dict[str, Template],
    region: Region | None,
    button_center: tuple[int, int, float],
    offset_y: int,
    config: dict | None = None,
) -> bool:
    if "level_lock_icon" not in templates:
        return False

    screen = capture_screen(region)
    row_center_x = button_center[0]
    scale = button_center[2]
    row_center_y = button_center[1] + scale_length(offset_y, config, scale)
    crop_left = row_center_x - scale_length(45, config, scale)
    crop_top = row_center_y - scale_length(10, config, scale)
    crop_width = scale_length(24, config, scale)
    crop_height = scale_length(22, config, scale)

    local_left = crop_left - screen.origin_x
    local_top = crop_top - screen.origin_y
    if (
        local_left < 0
        or local_top < 0
        or local_left + crop_width > screen.rgb.shape[1]
        or local_top + crop_height > screen.rgb.shape[0]
    ):
        return False

    crop_rgb = screen.rgb[local_top : local_top + crop_height, local_left : local_left + crop_width, :]
    crop_image = Image.fromarray(crop_rgb, mode="RGB")
    crop_screen = ScreenShot(crop_image, crop_rgb, crop_left, crop_top)
    match = find_template(crop_screen, templates["level_lock_icon"], tolerance=80, minimum_match=0.70)
    return match is not None


def level_range_options_visible(
    templates: dict[str, Template],
    region: Region | None,
) -> bool:
    screen = capture_screen(region)
    match = find_template(screen, templates["level_range_option_20_40"], tolerance=60, minimum_match=0.70)
    return match is not None


def choose_unlocked_level_range(
    target: str,
    templates: dict[str, Template],
    region: Region | None,
    button_center: tuple[int, int, float],
    config: dict,
) -> str:
    if not level_range_row_is_locked(
        templates,
        region,
        button_center,
        int(LEVEL_RANGE_CHOICES[target]["offset_y"]),
        config,
    ):
        return target

    logging.warning("%s is locked on this screen.", LEVEL_RANGE_CHOICES[target]["label"])
    if config.get("locked_level_fallback", "lower") != "lower":
        return target

    target_index = LEVEL_RANGE_KEYS.index(target)
    for key in reversed(LEVEL_RANGE_KEYS[:target_index]):
        if not level_range_row_is_locked(
            templates,
            region,
            button_center,
            int(LEVEL_RANGE_CHOICES[key]["offset_y"]),
            config,
        ):
            logging.info("fallback level range: %s", LEVEL_RANGE_CHOICES[key]["label"])
            return key

    logging.warning("all lower level ranges look locked; trying requested range anyway.")
    return target


def ensure_level_range(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
) -> bool:
    target = str(config.get("target_level_range") or "20_40")
    if target not in LEVEL_RANGE_CHOICES:
        logging.warning("unknown target level range: %s", target)
        return False

    tolerance = match_tolerance(config)
    minimum = minimum_match(config)
    click_delay = float(config["click_delay_seconds"])
    choice = LEVEL_RANGE_CHOICES[target]

    if target == "20_40":
        current = find("level_range_button_20_40", templates, region, tolerance, minimum)
        if current:
            logging.info("level range already %s.", choice["label"])
            return True

    center = level_range_button_center(templates, region, tolerance, minimum, config)
    if not center:
        logging.warning("level range dropdown was not found.")
        return False

    if not level_range_options_visible(templates, region):
        click_at(center[0], center[1], click_delay)
        time.sleep(0.2)
        if not level_range_options_visible(templates, region):
            logging.warning("level range dropdown did not open.")
            return False

    selected = choose_unlocked_level_range(target, templates, region, center, config)
    choice = LEVEL_RANGE_CHOICES[selected]
    logging.info("select level range: %s", choice["label"])
    click_at(center[0], center[1] + scale_length(int(choice["offset_y"]), config, center[2]), click_delay)
    time.sleep(0.2)
    if level_range_options_visible(templates, region):
        logging.info("level range dropdown remained open; closing it.")
        click_at(center[0], center[1], click_delay)
    return True


def ensure_level_range_20_40(
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
    click_delay: float,
) -> bool:
    config = DEFAULT_CONFIG.copy()
    config["match_tolerance"] = tolerance
    config["minimum_match"] = minimum_match
    config["click_delay_seconds"] = click_delay
    config["target_level_range"] = "20_40"
    return ensure_level_range(templates, region, config)


def auto_fill_visible(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
    timeout_seconds: float = 0.5,
) -> bool:
    return find_auto_fill_button(templates, region, config, timeout_seconds=timeout_seconds) is not None


def auto_fill_match_has_context(
    screen: ScreenShot,
    match: Match,
    templates: dict[str, Template],
    config: dict,
) -> bool:
    dropdown_center_x = match.center_x + scale_length(68, config, match)
    dropdown_center_y = match.center_y
    radius = max(14, scale_length(24, config, match))
    search_region = Region(
        left=dropdown_center_x - radius,
        top=dropdown_center_y - radius,
        width=radius * 2,
        height=radius * 2,
    )
    dropdown = find_template_in_screen_region(
        screen,
        templates["auto_fill_dropdown"],
        search_region,
        control_match_tolerance(config),
        control_minimum_match(config),
    )
    if dropdown is None:
        return False

    level_center_x = match.center_x + scale_length(150, config, match)
    level_center_y = match.center_y - scale_length(223, config, match)
    level_radius_x = max(90, scale_length(110, config, match))
    level_radius_y = max(30, scale_length(40, config, match))
    level_region = Region(
        left=level_center_x - level_radius_x,
        top=level_center_y - level_radius_y,
        width=level_radius_x * 2,
        height=level_radius_y * 2,
    )
    level_tolerance = max(control_match_tolerance(config), 90)
    level_minimum = min(control_minimum_match(config), 0.95)
    for name in ("level_range_button_20_40", "level_range_button_sample"):
        level = find_template_in_screen_region(
            screen,
            templates[name],
            level_region,
            level_tolerance,
            level_minimum,
        )
        if level is not None:
            return True

    mode_center_x = match.center_x
    mode_center_y = match.center_y - scale_length(223, config, match)
    mode_radius_x = max(90, scale_length(115, config, match))
    mode_radius_y = max(30, scale_length(40, config, match))
    mode_region = Region(
        left=mode_center_x - mode_radius_x,
        top=mode_center_y - mode_radius_y,
        width=mode_radius_x * 2,
        height=mode_radius_y * 2,
    )
    mode = find_template_in_screen_region(
        screen,
        templates["cube_mode_option_combine"],
        mode_region,
        max(control_match_tolerance(config), int(config.get("cube_mode_option_match_tolerance", 120))),
        min(control_minimum_match(config), float(config.get("cube_mode_option_minimum_match", 0.80))),
    )
    return mode is not None
    return False


def find_auto_fill_button(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
    timeout_seconds: float = 0.5,
) -> Match | None:
    deadline = time.monotonic() + timeout_seconds
    tolerance = control_match_tolerance(config)
    minimum = control_minimum_match(config)
    level_tolerance = max(tolerance, 90)
    level_minimum = min(minimum, 0.95)

    while time.monotonic() < deadline:
        screen = capture_screen(region)
        level_match = None
        for level_name in ("level_range_button_20_40", "level_range_button_sample"):
            level_match = find_template(screen, templates[level_name], level_tolerance, level_minimum)
            if level_match:
                break
        if level_match:
            expected_x = level_match.center_x - scale_length(150, config, level_match)
            expected_y = level_match.center_y + scale_length(223, config, level_match)
            radius_x = max(45, scale_length(65, config, level_match))
            radius_y = max(28, scale_length(40, config, level_match))
            anchored_region = Region(
                left=expected_x - radius_x,
                top=expected_y - radius_y,
                width=radius_x * 2,
                height=radius_y * 2,
            )
            for name in AUTO_FILL_BUTTON_TEMPLATES:
                match = find_template_in_screen_region(screen, templates[name], anchored_region, tolerance, minimum)
                if not match:
                    continue
                if auto_fill_match_has_context(screen, match, templates, config):
                    logging.info(
                        "found %-15s at (%d, %d) score=%.3f",
                        name,
                        match.center_x,
                        match.center_y,
                        match.score,
                    )
                    return match
                logging.debug(
                    "reject %-15s at (%d, %d): anchored auto-fill context was not found",
                    name,
                    match.center_x,
                    match.center_y,
                )

        mode_match = find_template(
            screen,
            templates["cube_mode_option_combine"],
            max(tolerance, int(config.get("cube_mode_option_match_tolerance", 120))),
            min(minimum, float(config.get("cube_mode_option_minimum_match", 0.80))),
        )
        if mode_match:
            expected_x = mode_match.center_x
            expected_y = mode_match.center_y + scale_length(223, config, mode_match)
            radius_x = max(45, scale_length(65, config, mode_match))
            radius_y = max(28, scale_length(40, config, mode_match))
            anchored_region = Region(
                left=expected_x - radius_x,
                top=expected_y - radius_y,
                width=radius_x * 2,
                height=radius_y * 2,
            )
            for name in AUTO_FILL_BUTTON_TEMPLATES:
                match = find_template_in_screen_region(screen, templates[name], anchored_region, tolerance, minimum)
                if not match:
                    continue
                if auto_fill_match_has_context(screen, match, templates, config):
                    logging.info(
                        "found %-15s at (%d, %d) score=%.3f",
                        name,
                        match.center_x,
                        match.center_y,
                        match.score,
                    )
                    return match
                logging.debug(
                    "reject %-15s at (%d, %d): mode-anchored auto-fill context was not found",
                    name,
                    match.center_x,
                    match.center_y,
                )

        for name in AUTO_FILL_BUTTON_TEMPLATES:
            match = find_template(screen, templates[name], tolerance, minimum)
            if not match:
                continue
            if auto_fill_match_has_context(screen, match, templates, config):
                logging.info("found %-15s at (%d, %d) score=%.3f", name, match.center_x, match.center_y, match.score)
                return match
            logging.debug(
                "reject %-15s at (%d, %d): auto-fill dropdown context was not found",
                name,
                match.center_x,
                match.center_y,
            )
        time.sleep(0.15)
    return None


def cube_slot_centers_from_auto_fill(reference: Match, config: dict) -> list[tuple[int, int]]:
    offsets = config.get("cube_slot_offsets_from_auto_fill", DEFAULT_CONFIG["cube_slot_offsets_from_auto_fill"])
    x_offsets = offsets.get("x", DEFAULT_CONFIG["cube_slot_offsets_from_auto_fill"]["x"])
    y_offsets = offsets.get("y", DEFAULT_CONFIG["cube_slot_offsets_from_auto_fill"]["y"])
    centers: list[tuple[int, int]] = []
    for y_offset in y_offsets:
        for x_offset in x_offsets:
            centers.append(
                (
                    reference.center_x + scale_length(int(x_offset), config, reference),
                    reference.center_y + scale_length(int(y_offset), config, reference),
                )
            )
    return centers


def cube_slot_is_occupied(crop_rgb: np.ndarray, config: dict) -> bool:
    if crop_rgb.size == 0:
        return False

    rgb = crop_rgb.astype(np.int16)
    luma = rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    color_fraction = float(((luma > 45) & (saturation > 25)).mean())
    detail_fraction = float(((luma > 55) | (saturation > 35)).mean())
    luma_std = float(luma.std())

    return (
        color_fraction >= float(config.get("cube_slot_color_fraction", 0.05))
        or (
            detail_fraction >= float(config.get("cube_slot_detail_fraction", 0.06))
            and luma_std >= float(config.get("cube_slot_luma_std", 22.0))
        )
    )


def count_filled_cube_slots_from_screen(
    screen: ScreenShot,
    reference: Match,
    config: dict,
) -> tuple[int, int]:
    probe_size = max(12, scale_length(int(config.get("cube_slot_probe_size", 26)), config, reference))
    half = probe_size // 2
    filled = 0
    visible = 0

    for center_x, center_y in cube_slot_centers_from_auto_fill(reference, config):
        local_left = center_x - half - screen.origin_x
        local_top = center_y - half - screen.origin_y
        local_right = local_left + probe_size
        local_bottom = local_top + probe_size
        if (
            local_left < 0
            or local_top < 0
            or local_right > screen.rgb.shape[1]
            or local_bottom > screen.rgb.shape[0]
        ):
            continue

        visible += 1
        crop = screen.rgb[local_top:local_bottom, local_left:local_right, :]
        if cube_slot_is_occupied(crop, config):
            filled += 1

    return filled, visible


def find_ready_combine_button(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
    auto_fill: Match,
    timeout_seconds: float = 2.0,
) -> Match | None:
    required_slots = max(1, int(config.get("cube_required_filled_slots", 9)))
    tolerance = control_match_tolerance(config)
    minimum = control_minimum_match(config)
    deadline = time.monotonic() + timeout_seconds
    last_filled = 0
    last_visible = 0

    while time.monotonic() < deadline:
        screen = capture_screen(region)
        filled, visible = count_filled_cube_slots_from_screen(screen, auto_fill, config)
        last_filled = filled
        last_visible = visible
        if visible < required_slots:
            logging.warning("cube slot probe saw only %d/%d slots; check capture region.", visible, required_slots)
            return None
        if filled < required_slots:
            time.sleep(0.2)
            continue

        offset = config.get("combine_button_offset_from_auto_fill", DEFAULT_CONFIG["combine_button_offset_from_auto_fill"])
        radius = config.get("combine_button_search_radius", DEFAULT_CONFIG["combine_button_search_radius"])
        expected_x = auto_fill.center_x + scale_length(int(offset.get("x", 137)), config, auto_fill)
        expected_y = auto_fill.center_y + scale_length(int(offset.get("y", 0)), config, auto_fill)
        button_template = templates["combine_ready"]
        radius_x = max(button_template.width // 2 + 8, scale_length(int(radius.get("x", 62)), config, auto_fill))
        radius_y = max(button_template.height // 2 + 6, scale_length(int(radius.get("y", 28)), config, auto_fill))
        button_region = Region(
            left=expected_x - radius_x,
            top=expected_y - radius_y,
            width=radius_x * 2,
            height=radius_y * 2,
        )
        ready = find_template_in_screen_region(
            screen,
            button_template,
            button_region,
            tolerance,
            minimum,
        )
        if ready:
            logging.info(
                "combine button confirmed: filled_slots=%d/%d at (%d, %d) score=%.3f",
                filled,
                required_slots,
                ready.center_x,
                ready.center_y,
                ready.score,
            )
            return ready

        logging.debug("cube slots are filled, but combine button was not found near expected position.")
        time.sleep(0.2)

    logging.info("cube is not ready to combine: filled_slots=%d/%d visible_slots=%d", last_filled, required_slots, last_visible)
    return None


def close_cube_mode_dropdown_if_needed(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
    click_delay: float,
) -> None:
    if auto_fill_visible(templates, region, config, timeout_seconds=0.4):
        return

    tolerance = control_match_tolerance(config)
    minimum = control_minimum_match(config)
    cube_ui = wait_for(
        ("combine_ready", "combine_tab", "auto_fill_dropdown"),
        templates,
        region,
        tolerance,
        minimum,
        timeout_seconds=0.4,
    )
    if not cube_ui:
        return

    center = level_range_button_center(templates, region, tolerance, minimum, config)
    if not center:
        return

    mode_center = (center[0] - scale_length(155, config, center[2]), center[1], center[2])
    logging.info("close cube mode dropdown via combine option.")
    click_cube_combine_option_by_offset(mode_center, config, click_delay)
    time.sleep(0.2)


def click_cube_combine_option_by_offset(
    button_center: tuple[int, int, float],
    config: dict,
    click_delay: float,
) -> None:
    option_y = button_center[1] + scale_length(int(config.get("cube_mode_combine_option_offset_y", 29)), config, button_center[2])
    logging.info("select cube combine option by offset at (%d, %d)", button_center[0], option_y)
    click_at(button_center[0], option_y, click_delay)


def cube_mode_button_center(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
) -> tuple[int, int, float] | None:
    center = level_range_button_center(
        templates,
        region,
        control_match_tolerance(config),
        control_minimum_match(config),
        config,
    )
    if not center:
        return None
    return center[0] - scale_length(155, config, center[2]), center[1], center[2]


def cube_mode_is_combine(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
) -> bool:
    center = cube_mode_button_center(templates, region, config)
    if not center:
        return False
    search_region = Region(
        left=center[0] - scale_length(90, config, center[2]),
        top=center[1] - scale_length(24, config, center[2]),
        width=scale_length(180, config, center[2]),
        height=scale_length(48, config, center[2]),
    )
    match = wait_for(
        ("cube_mode_option_combine", "combine_tab"),
        templates,
        search_region,
        max(control_match_tolerance(config), int(config.get("cube_mode_option_match_tolerance", 120))),
        min(control_minimum_match(config), float(config.get("cube_mode_option_minimum_match", 0.80))),
        timeout_seconds=0.4,
    )
    return match is not None


def ensure_cube_combine_mode(
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
    click_delay: float,
    config: dict,
) -> bool:
    control_tolerance = control_match_tolerance(config)
    control_minimum = control_minimum_match(config)
    existing_auto_fill = find_auto_fill_button(templates, region, config, timeout_seconds=0.8)
    existing_tab = None
    if not existing_auto_fill:
        existing_tab = wait_for(
            ("combine_ready", "combine_tab"),
            templates,
            region,
            control_tolerance,
            control_minimum,
            timeout_seconds=0.4,
        )
    if existing_auto_fill or existing_tab:
        if cube_mode_is_combine(templates, region, config):
            close_cube_mode_dropdown_if_needed(templates, region, config, click_delay)
            return True
        logging.info("cube UI is visible but mode is not combine; switching mode.")

    center = level_range_button_center(templates, region, tolerance, minimum_match, config)
    if not center:
        return False

    mode_center = (center[0] - scale_length(155, config, center[2]), center[1], center[2])

    # If the mode dropdown is already open, selecting the first row switches back to combine.
    click_cube_combine_option_by_offset(mode_center, config, click_delay)
    switched = wait_for(
        ("auto_fill_dropdown", "combine_ready", "combine_tab"),
        templates,
        region,
        control_tolerance,
        control_minimum,
        timeout_seconds=1.0,
    )
    if switched:
        close_cube_mode_dropdown_if_needed(templates, region, config, click_delay)
        return True

    logging.info("open cube mode dropdown at (%d, %d)", mode_center[0], mode_center[1])
    click_at(mode_center[0], mode_center[1], click_delay)
    time.sleep(0.15)
    click_cube_combine_option_by_offset(mode_center, config, click_delay)

    switched = wait_for(
        ("auto_fill_dropdown", "combine_ready", "combine_tab"),
        templates,
        region,
        control_tolerance,
        control_minimum,
        timeout_seconds=2.0,
    )
    if switched:
        close_cube_mode_dropdown_if_needed(templates, region, config, click_delay)
        return True
    return False


def ensure_cube_open(
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
    click_delay: float,
) -> bool:
    config = get_active_config() or DEFAULT_CONFIG
    control_tolerance = control_match_tolerance(config)
    control_minimum = control_minimum_match(config)
    auto_fill = find_auto_fill_button(templates, region, config, timeout_seconds=0.4)
    if auto_fill:
        logging.info("cube/combine UI already visible.")
        return ensure_cube_combine_mode(templates, region, tolerance, minimum_match, click_delay, config)

    if not click_if_found("cube", templates, region, tolerance, minimum_match, click_delay):
        if not click_if_found("open_menu", templates, region, tolerance, minimum_match, click_delay):
            logging.warning("open menu button was not found.")
        cube_match = wait_for(("cube",), templates, region, tolerance, minimum_match, timeout_seconds=3.0)
        if not cube_match:
            logging.error("cube button was not found.")
            return False
        click_match(cube_match, click_delay)

    combine_ui = find_auto_fill_button(templates, region, config, timeout_seconds=3.0)
    if not combine_ui:
        config = get_active_config() or DEFAULT_CONFIG
        if not ensure_cube_combine_mode(templates, region, tolerance, minimum_match, click_delay, config):
            logging.error("combine UI did not appear after opening cube.")
            return False

    click_if_found("combine_tab", templates, region, tolerance, minimum_match, click_delay)
    close_cube_mode_dropdown_if_needed(templates, region, config, click_delay)
    return True


def clear_cube_items(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
    reference: Match | None = None,
    reason: str = "",
) -> bool:
    tolerance = max(match_tolerance(config), 70)
    minimum = min(minimum_match(config), 0.90)
    click_delay = float(config["click_delay_seconds"])
    attempts = max(1, int(config.get("cube_clear_attempts", 2)))
    offset = config.get("back_offset_from_auto_fill", DEFAULT_CONFIG["back_offset_from_auto_fill"])
    clicked = False

    if reason:
        logging.info("clear cube items: %s", reason)

    for attempt in range(attempts):
        back = wait_for(("back",), templates, region, tolerance, minimum, timeout_seconds=0.8)
        if back:
            click_match(back, click_delay)
            clicked = True
            continue

        if reference:
            x = reference.center_x + scale_length(int(offset.get("x", -11)), config, reference)
            y = reference.center_y + scale_length(int(offset.get("y", -50)), config, reference)
            logging.info("back button not found; click fallback clear position at (%d, %d)", x, y)
            click_at(x, y, click_delay)
            clicked = True
            continue

        logging.warning("back button was not found, and no fallback reference is available.")
        break

    return clicked


def combine_until_done(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
    category: str,
) -> int:
    tolerance = control_match_tolerance(config)
    minimum = control_minimum_match(config)
    click_delay = float(config["click_delay_seconds"])
    after_combine_delay = float(config["after_combine_delay_seconds"])
    max_combines = int(config["max_combines_per_run"])
    no_progress_limit = int(config["no_progress_limit"])
    force_level_range = bool(config.get("force_level_range_20_40", False))

    combines = 0
    misses = 0

    for _ in range(max_combines):
        if force_level_range:
            ensure_level_range(templates, region, config)

        auto_fill = find_auto_fill_button(templates, region, config, timeout_seconds=2.0)
        if not auto_fill:
            logging.info("auto-fill button is no longer visible.")
            break
        click_match(auto_fill, click_delay)

        ready = find_ready_combine_button(
            templates,
            region,
            config,
            auto_fill,
            timeout_seconds=2.0,
        )
        if not ready:
            misses += 1
            logging.info("nothing combinable after auto-fill. miss=%d/%d", misses, no_progress_limit)
            clear_cube_items(
                templates,
                region,
                config,
                reference=auto_fill,
                reason="auto-fill did not produce a combinable set.",
            )
            if misses >= no_progress_limit:
                break
            continue

        misses = 0
        click_match(ready, click_delay)
        combines += 1
        logging.info("combine started. category=%s count=%d", category, combines)
        time.sleep(after_combine_delay)

    if combines >= max_combines:
        logging.warning("max_combines_per_run reached; stopping this run to avoid an infinite loop.")
    return combines
