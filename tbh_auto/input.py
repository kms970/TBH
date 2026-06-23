from __future__ import annotations

import logging

from .models import Match, Region, Template
from .vision import find
from .windows import click_at, scroll_at


def click_match(match: Match, delay_seconds: float) -> None:
    logging.info("click %-15s at (%d, %d)", match.name, match.center_x, match.center_y)
    click_at(match.center_x, match.center_y, delay_seconds)


def click_if_found(
    name: str,
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
    delay_seconds: float,
) -> bool:
    match = find(name, templates, region, tolerance, minimum_match)
    if not match:
        return False
    click_match(match, delay_seconds)
    return True
