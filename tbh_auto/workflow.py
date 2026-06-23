from __future__ import annotations

import logging

from .config import match_tolerance, minimum_match
from .constants import CATEGORY_OPTION_TEMPLATES
from .cube import clear_cube_items, combine_until_done, ensure_cube_open, find_auto_fill_button, select_auto_fill_category
from .models import Region, Template
from .rewards import close_cube_for_reward_boxes, open_reward_boxes
from .state import set_active_config
from .storage import finish_storage_to_bag


def run_once(templates: dict[str, Template], region: Region | None, config: dict) -> int:
    set_active_config(config)
    tolerance = match_tolerance(config)
    minimum = minimum_match(config)
    click_delay = float(config["click_delay_seconds"])

    logging.info("automation run started.")
    if not region:
        logging.warning("search_region is not configured; scanning the entire desktop.")

    if bool(config.get("open_reward_boxes_before_combine", True)):
        close_cube_for_reward_boxes(templates, region, config)
        open_reward_boxes(templates, region, config)

    if not ensure_cube_open(templates, region, tolerance, minimum, click_delay):
        return 0

    combines = 0
    categories = config.get("auto_fill_categories", ["equipment", "material"])
    for category in categories:
        if category not in CATEGORY_OPTION_TEMPLATES:
            logging.warning("skipping unknown auto-fill category: %s", category)
            continue
        reference = find_auto_fill_button(templates, region, config, timeout_seconds=0.8)
        clear_cube_items(
            templates,
            region,
            config,
            reference=reference,
            reason=f"before selecting {category}.",
        )
        select_auto_fill_category(category, templates, region, tolerance, minimum, click_delay, config)
        combines += combine_until_done(templates, region, config, category)
        reference = find_auto_fill_button(templates, region, config, timeout_seconds=0.8)
        clear_cube_items(
            templates,
            region,
            config,
            reference=reference,
            reason=f"after finishing {category}.",
        )

    finish_storage_to_bag(templates, region, config)
    logging.info("automation run finished. combines=%d", combines)
    return combines
