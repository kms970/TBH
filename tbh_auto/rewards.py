from __future__ import annotations

import logging
import time
from collections import deque
from typing import Iterable

import numpy as np

from .config import (
    match_tolerance,
    minimum_match,
    reward_box_minimum_match,
    scale_length,
    screen_scale_factor,
)
from .constants import DEFAULT_CONFIG, REWARD_BOX_TEMPLATES
from .cube import level_range_button_center
from .input import click_match
from .models import Match, Region, ScreenShot, Template
from .vision import find_template
from .windows import capture_screen, click_at


def wait_for_reward_box(
    names: Iterable[str],
    templates: dict[str, Template],
    region: Region | None,
    tolerances: Iterable[int],
    minimum_match: float,
    timeout_seconds: float,
    poll_seconds: float = 0.25,
) -> Match | None:
    deadline = time.monotonic() + timeout_seconds
    names = tuple(names)
    tolerances = tuple(tolerances)
    while time.monotonic() < deadline:
        screen = capture_screen(region)
        for name in names:
            for tolerance in tolerances:
                match = find_template(screen, templates[name], tolerance, minimum_match)
                if match:
                    logging.info(
                        "found %-15s at (%d, %d) score=%.3f tolerance=%d",
                        name,
                        match.center_x,
                        match.center_y,
                        match.score,
                        tolerance,
                    )
                    return match
        time.sleep(poll_seconds)
    return None


def reward_box_position_key(match: Match, config: dict) -> tuple[str, int, int]:
    bucket = max(1, scale_length(int(config.get("reward_box_same_position_bucket", 8)), config, match))
    return (
        match.name,
        int(round(match.center_x / bucket)),
        int(round(match.center_y / bucket)),
    )


def classify_reward_bubble(crop_rgb: np.ndarray, allowed_names: set[str]) -> tuple[str, float] | None:
    rgb = crop_rgb.astype(np.int16)
    red = rgb[:, :, 0]
    green = rgb[:, :, 1]
    blue = rgb[:, :, 2]

    white_pixels = (red > 205) & (green > 205) & (blue > 205)
    brown_pixels = (
        (red > 75)
        & (red < 190)
        & (green > 35)
        & (green < 135)
        & (blue < 120)
        & (red > green + 10)
    )
    blue_pixels = (
        (blue > 120)
        & (green > 70)
        & (red < 120)
        & (blue > red + 35)
    )
    dark_detail_pixels = (red < 80) & (green < 80) & (blue < 90)

    white_fraction = float(white_pixels.mean())
    dark_fraction = float(dark_detail_pixels.mean())
    brown_fraction = float(brown_pixels.mean())
    blue_fraction = float(blue_pixels.mean())

    if white_fraction < 0.13 or dark_fraction < 0.006:
        return None

    brown_score = min(1.0, white_fraction * 0.55 + brown_fraction * 8.0 + dark_fraction * 1.5)
    blue_score = min(1.0, white_fraction * 0.55 + blue_fraction * 10.0 + dark_fraction * 1.3)

    if (
        "reward_chest_bubble" in allowed_names
        and brown_fraction >= 0.030
        and brown_score >= blue_score - 0.05
    ):
        return "reward_chest_bubble", brown_score
    if "reward_blue_box_bubble" in allowed_names and blue_fraction >= 0.025:
        return "reward_blue_box_bubble", blue_score
    return None


def reward_box_match_has_valid_context(screen: ScreenShot, match: Match, config: dict) -> bool:
    if not bool(config.get("reward_box_context_validation", True)):
        return True

    pad = max(2, scale_length(5, config, match))
    local_left = max(0, match.left - screen.origin_x - pad)
    local_top = max(0, match.top - screen.origin_y - pad)
    local_right = min(screen.rgb.shape[1], match.left - screen.origin_x + match.width + pad)
    local_bottom = min(screen.rgb.shape[0], match.top - screen.origin_y + match.height + pad)
    if local_right <= local_left or local_bottom <= local_top:
        return False

    crop_rgb = screen.rgb[local_top:local_bottom, local_left:local_right, :]
    classified = classify_reward_bubble(crop_rgb, {match.name})
    if not classified:
        return False

    classified_name, shape_score = classified
    minimum_shape_score = float(config.get("reward_box_shape_min_score", 0.62))
    return classified_name == match.name and shape_score >= minimum_shape_score


def find_reward_bubble_by_shape(
    screen: ScreenShot,
    names: Iterable[str],
    config: dict,
    blocked_names: set[str] | None = None,
    blocked_positions: set[tuple[str, int, int]] | None = None,
    row_center_y: int | None = None,
) -> Match | None:
    if not bool(config.get("reward_box_shape_fallback", True)):
        return None

    allowed_names = set(names) & set(REWARD_BOX_TEMPLATES)
    if blocked_names:
        allowed_names -= blocked_names
    if not allowed_names:
        return None

    scale = screen_scale_factor(config)
    min_w = max(18, int(round(32 * scale)))
    max_w = max(min_w + 1, int(round(90 * scale)))
    min_h = max(14, int(round(22 * scale)))
    max_h = max(min_h + 1, int(round(65 * scale)))
    min_area = max(120, int(round(350 * scale * scale)))
    minimum_shape_score = float(config.get("reward_box_shape_min_score", 0.62))

    rgb = screen.rgb
    whiteish = (rgb[:, :, 0] > 210) & (rgb[:, :, 1] > 210) & (rgb[:, :, 2] > 210)
    visited = np.zeros(whiteish.shape, dtype=bool)
    height, width = whiteish.shape
    ys, xs = np.nonzero(whiteish)
    candidates: list[tuple[Match, float]] = []

    for start_y, start_x in zip(ys, xs):
        if visited[start_y, start_x]:
            continue
        queue: deque[tuple[int, int]] = deque([(int(start_y), int(start_x))])
        visited[start_y, start_x] = True
        min_x = max_x = int(start_x)
        min_y = max_y = int(start_y)
        count = 0

        while queue:
            y, x = queue.popleft()
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
                if 0 <= ny < height and 0 <= nx < width and whiteish[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))

        box_w = max_x - min_x + 1
        box_h = max_y - min_y + 1
        if count < min_area or box_w < min_w or box_w > max_w or box_h < min_h or box_h > max_h:
            continue

        aspect = box_w / max(1, box_h)
        white_density = count / max(1, box_w * box_h)
        if aspect < 0.9 or aspect > 3.8 or white_density < 0.10:
            continue

        pad = max(2, int(round(4 * scale)))
        crop_left = max(0, min_x - pad)
        crop_top = max(0, min_y - pad)
        crop_right = min(width, max_x + pad + 1)
        crop_bottom = min(height, max_y + pad + 1)
        crop_rgb = rgb[crop_top:crop_bottom, crop_left:crop_right, :]
        classified = classify_reward_bubble(crop_rgb, set(REWARD_BOX_TEMPLATES))
        if not classified:
            continue

        name, score = classified
        if score < minimum_shape_score:
            continue
        match = Match(
            name=name,
            left=int(screen.origin_x + crop_left),
            top=int(screen.origin_y + crop_top),
            width=int(crop_right - crop_left),
            height=int(crop_bottom - crop_top),
            score=float(score),
            mean_diff=0.0,
            scale=scale,
        )
        if row_center_y is not None:
            row_tolerance = scale_length(int(config.get("reward_box_row_tolerance", 80)), config)
            if abs(match.center_y - row_center_y) > row_tolerance:
                continue
        if blocked_positions and reward_box_position_key(match, config) in blocked_positions:
            continue
        candidates.append((match, score))

    row_tolerance = scale_length(int(config.get("reward_box_row_tolerance", 80)), config)
    pair_min_distance = scale_length(int(config.get("reward_box_pair_min_distance", 45)), config)
    pair_max_distance = scale_length(int(config.get("reward_box_pair_max_distance", 140)), config)

    def has_reward_pair(match: Match) -> bool:
        for other, _score in candidates:
            if other is match:
                continue
            dx = abs(other.center_x - match.center_x)
            dy = abs(other.center_y - match.center_y)
            if dy <= row_tolerance and pair_min_distance <= dx <= pair_max_distance:
                return True
        return False

    best: Match | None = None
    best_rank = -1.0
    for match, score in candidates:
        if match.name not in allowed_names:
            continue
        paired = has_reward_pair(match)
        if row_center_y is None and match.name == "reward_blue_box_bubble" and not paired:
            continue
        rank = score + (0.35 if paired else 0.0)
        if row_center_y is not None:
            rank += 0.25
        if rank > best_rank:
            best_rank = rank
            best = match

    if best:
        logging.info(
            "found %-15s by bubble shape at (%d, %d) score=%.3f",
            best.name,
            best.center_x,
            best.center_y,
            best.score,
        )
    return best


def find_reward_box_for_opening(
    names: Iterable[str],
    templates: dict[str, Template],
    region: Region | None,
    tolerances: Iterable[int],
    minimum_match: float,
    config: dict,
    blocked_names: set[str],
    blocked_positions: set[tuple[str, int, int]],
    row_center_y: int | None,
    timeout_seconds: float,
    poll_seconds: float = 0.25,
) -> Match | None:
    deadline = time.monotonic() + timeout_seconds
    names = tuple(names)
    tolerances = tuple(tolerances)
    while time.monotonic() < deadline:
        screen = capture_screen(region)
        for name in names:
            if name in blocked_names:
                continue
            for tolerance in tolerances:
                match = find_template(screen, templates[name], tolerance, minimum_match)
                if not match:
                    continue
                if reward_box_position_key(match, config) in blocked_positions:
                    continue
                if row_center_y is not None:
                    row_tolerance = scale_length(int(config.get("reward_box_row_tolerance", 80)), config, match)
                    if abs(match.center_y - row_center_y) > row_tolerance:
                        continue
                if not reward_box_match_has_valid_context(screen, match, config):
                    logging.debug(
                        "reject %-15s at (%d, %d): reward-box context validation failed",
                        name,
                        match.center_x,
                        match.center_y,
                    )
                    continue
                logging.info(
                    "found %-15s at (%d, %d) score=%.3f tolerance=%d",
                    name,
                    match.center_x,
                    match.center_y,
                    match.score,
                    tolerance,
                )
                return match
        fallback = find_reward_bubble_by_shape(
            screen,
            names,
            config,
            blocked_names,
            blocked_positions,
            row_center_y,
        )
        if fallback:
            return fallback
        time.sleep(poll_seconds)
    return None


def open_reward_boxes(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
) -> int:
    if not bool(config.get("open_reward_boxes_before_combine", True)):
        logging.info("reward box opening is disabled.")
        return 0

    base_tolerance = int(config.get("reward_box_match_tolerance", config["match_tolerance"]))
    tolerances = tuple(dict.fromkeys([80, 60, base_tolerance]))
    minimum_match = reward_box_minimum_match(config)
    click_delay = float(config.get("reward_box_click_delay_seconds", 0.8))
    max_opens = int(config.get("reward_box_max_opens", 60))
    same_position_limit = max(0, int(config.get("reward_box_same_position_limit", 30)))
    max_clicks_by_type = config.get("reward_box_max_clicks_by_type", {})
    if not isinstance(max_clicks_by_type, dict):
        max_clicks_by_type = {}
    search_region = region
    relative_area = config.get("reward_box_search_area_from_region")
    if bool(config.get("reward_box_search_whole_region", True)):
        search_region = region
    elif region and isinstance(relative_area, dict):
        search_region = Region(
            left=region.left + scale_length(int(relative_area.get("left", 0)), config),
            top=region.top + scale_length(int(relative_area.get("top", 0)), config),
            width=scale_length(int(relative_area.get("width", region.width)), config),
            height=scale_length(int(relative_area.get("height", region.height)), config),
        )
    opened = 0
    type_clicks: dict[str, int] = {}
    blocked_names: set[str] = set()
    position_clicks: dict[tuple[str, int, int], int] = {}
    blocked_positions: set[tuple[str, int, int]] = set()
    reward_row_center_y: int | None = None

    search_attempts = 0
    max_search_attempts = max(max_opens * 3, max_opens + len(REWARD_BOX_TEMPLATES) * 4)

    while opened < max_opens and search_attempts < max_search_attempts:
        names = list(REWARD_BOX_TEMPLATES)
        rotation = search_attempts % len(names)
        names = names[rotation:] + names[:rotation]
        search_attempts += 1
        match = find_reward_box_for_opening(
            names,
            templates,
            search_region,
            tolerances,
            minimum_match,
            config,
            blocked_names,
            blocked_positions,
            reward_row_center_y,
            timeout_seconds=0.7,
        )
        if not match:
            break

        type_limit = int(max_clicks_by_type.get(match.name, 0) or 0)
        clicked_type = type_clicks.get(match.name, 0)
        if type_limit and clicked_type >= type_limit:
            blocked_names.add(match.name)
            logging.info("%s click limit reached: %d", match.name, clicked_type)
            continue

        position_key = reward_box_position_key(match, config)
        clicked_same_position = position_clicks.get(position_key, 0)
        if same_position_limit and clicked_same_position >= same_position_limit:
            blocked_positions.add(position_key)
            logging.warning(
                "%s stayed at the same position after %d clicks; skipping it for this run.",
                match.name,
                clicked_same_position,
            )
            continue

        click_match(match, click_delay)
        if reward_row_center_y is None:
            reward_row_center_y = match.center_y
        type_clicks[match.name] = clicked_type + 1
        position_clicks[position_key] = clicked_same_position + 1
        opened += 1

    if opened >= max_opens:
        logging.warning("reward box open limit reached; stopping to avoid an infinite loop.")
    elif search_attempts >= max_search_attempts:
        logging.warning("reward box search limit reached; stopping to avoid an infinite loop.")
    logging.info("reward boxes opened: %d", opened)
    return opened


def close_cube_for_reward_boxes(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
) -> bool:
    if not bool(config.get("close_cube_before_reward_boxes", True)):
        return False

    tolerance = match_tolerance(config)
    minimum = minimum_match(config)
    click_delay = float(config["click_delay_seconds"])
    center = level_range_button_center(templates, region, tolerance, minimum, config)
    if not center:
        return False

    offset = config.get("cube_close_offset_from_level_button", DEFAULT_CONFIG["cube_close_offset_from_level_button"])
    x = center[0] + scale_length(int(offset.get("x", 46)), config, center[2])
    y = center[1] + scale_length(int(offset.get("y", -43)), config, center[2])
    logging.info("close cube before reward boxes at (%d, %d)", x, y)
    click_at(x, y, click_delay)
    time.sleep(0.3)
    return True
