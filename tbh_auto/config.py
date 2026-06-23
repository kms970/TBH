from __future__ import annotations

import json
import logging
import sys

from .constants import CURRENT_CONFIG_VERSION, DEFAULT_CONFIG, SCREEN_SCALE_CHOICES
from .paths import CONFIG_PATH, LOG_DIR


def configure_logging(verbose: bool) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "task_bar_hero_auto.log", encoding="utf-8"),
        ],
    )


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    try:
        raw_version = int(raw.get("config_schema_version", 1))
    except (TypeError, ValueError):
        raw_version = 1

    config = DEFAULT_CONFIG.copy()
    config.update(raw)
    migrated = False
    if raw_version < 2:
        config["force_level_range_20_40"] = False
        migrated = True
    if raw_version < 3:
        try:
            clear_attempts = int(config.get("cube_clear_attempts", DEFAULT_CONFIG["cube_clear_attempts"]))
        except (TypeError, ValueError):
            clear_attempts = DEFAULT_CONFIG["cube_clear_attempts"]
        config["cube_clear_attempts"] = max(clear_attempts, DEFAULT_CONFIG["cube_clear_attempts"])
        migrated = True
    if raw_version < 5:
        try:
            tolerance = int(config.get("match_tolerance", DEFAULT_CONFIG["match_tolerance"]))
        except (TypeError, ValueError):
            tolerance = DEFAULT_CONFIG["match_tolerance"]
        config["match_tolerance"] = max(tolerance, DEFAULT_CONFIG["match_tolerance"])
        config["multi_scale_matching"] = True
        migrated = True
    if raw_version < 6:
        config["search_region_follow_window"] = True
        migrated = True
    if raw_version < 8:
        config["auto_follow_window"] = True
        config["search_region_follow_window"] = True
        migrated = True
    if raw_version < CURRENT_CONFIG_VERSION:
        config["config_schema_version"] = CURRENT_CONFIG_VERSION
        migrated = True

    if config.get("click_mode") == "window_message":
        config["click_mode"] = "cursor"
        migrated = True
    max_clicks_by_type = config.get("reward_box_max_clicks_by_type")
    if isinstance(max_clicks_by_type, dict):
        total_reward_limit = sum(max(0, int(value)) for value in max_clicks_by_type.values())
        config["reward_box_max_opens"] = max(int(config.get("reward_box_max_opens", 0)), total_reward_limit)
    if migrated:
        save_config(config)
    return config


def save_config(config: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def screen_scale_factor(config: dict | None) -> float:
    if not config:
        return 1.0
    raw = str(config.get("game_screen_scale", "1x"))
    if raw in SCREEN_SCALE_CHOICES:
        return float(SCREEN_SCALE_CHOICES[raw]["factor"])
    try:
        return max(0.5, min(3.0, float(raw.rstrip("x"))))
    except ValueError:
        logging.warning("unknown game screen scale: %s; using 1x", raw)
        return 1.0


def reference_scale_factor(reference: object | None, config: dict | None) -> float:
    if reference is not None:
        if isinstance(reference, (int, float)):
            scale = float(reference)
        else:
            try:
                scale = float(getattr(reference, "scale"))
            except (TypeError, ValueError, AttributeError):
                scale = 0.0
        if scale > 0:
            return scale
    return screen_scale_factor(config)


def scale_length(value: int | float, config: dict | None, reference: object | None = None) -> int:
    return int(round(float(value) * reference_scale_factor(reference, config)))


def scale_offset(
    offset: tuple[int, int],
    config: dict | None,
    reference: object | None = None,
) -> tuple[int, int]:
    return scale_length(offset[0], config, reference), scale_length(offset[1], config, reference)


def match_tolerance(config: dict) -> int:
    base = int(config["match_tolerance"])
    if screen_scale_factor(config) == 1.0:
        return base
    return max(base, int(config.get("scaled_match_tolerance", 80)))


def minimum_match(config: dict) -> float:
    base = float(config["minimum_match"])
    if screen_scale_factor(config) == 1.0:
        return base
    return min(base, float(config.get("scaled_minimum_match", 0.975)))


def reward_box_minimum_match(config: dict) -> float:
    return float(config.get("reward_box_minimum_match", config["minimum_match"]))


def control_match_tolerance(config: dict) -> int:
    return max(match_tolerance(config), int(config.get("control_match_tolerance", 120)))


def control_minimum_match(config: dict) -> float:
    return min(minimum_match(config), float(config.get("control_minimum_match", 0.90)))


