from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from .config import screen_scale_factor
from .constants import SCREEN_SCALE_CHOICES, TEMPLATE_FILES
from .models import Match, Region, ScreenShot, Template
from .paths import TEMPLATE_DIR
from .windows import capture_screen


def choose_anchors(rgb: np.ndarray, mask: np.ndarray, count: int = 7) -> tuple[tuple[int, int, tuple[int, int, int]], ...]:
    coords = np.argwhere(mask)
    if coords.size == 0:
        h, w = mask.shape
        coords = np.array([[h // 2, w // 2]], dtype=np.int64)

    colors = rgb[coords[:, 0], coords[:, 1]].astype(np.int32)
    mean_color = colors.mean(axis=0)
    saturation = colors.max(axis=1) - colors.min(axis=1)
    contrast = np.abs(colors - mean_color).sum(axis=1)
    packed = (
        (colors[:, 0].astype(np.int64) << 16)
        | (colors[:, 1].astype(np.int64) << 8)
        | colors[:, 2].astype(np.int64)
    )
    unique, inverse, counts = np.unique(packed, return_inverse=True, return_counts=True)
    _ = unique
    rarity = 1.0 / counts[inverse]
    scores = saturation * 2.0 + contrast + rarity * 2000.0

    order = np.argsort(scores)[::-1]
    h, w = mask.shape
    min_distance = max(3, min(h, w) // 4)
    anchors: list[tuple[int, int, tuple[int, int, int]]] = []

    for idx in order:
        y, x = (int(coords[idx, 0]), int(coords[idx, 1]))
        if any((y - ay) ** 2 + (x - ax) ** 2 < min_distance**2 for ay, ax, _ in anchors):
            continue
        color = tuple(int(v) for v in rgb[y, x, :3])
        anchors.append((y, x, color))
        if len(anchors) >= count:
            break

    if not anchors:
        y, x = int(coords[0, 0]), int(coords[0, 1])
        anchors.append((y, x, tuple(int(v) for v in rgb[y, x, :3])))

    return tuple(anchors)


def template_scale_values(config: dict | None) -> tuple[float, ...]:
    primary = screen_scale_factor(config)
    values = [primary]
    if config is None or bool(config.get("multi_scale_matching", True)):
        for choice in SCREEN_SCALE_CHOICES.values():
            factor = float(choice["factor"])
            if all(abs(factor - existing) > 0.001 for existing in values):
                values.append(factor)
    return tuple(values)


def build_template(name: str, path: Path, image: Image.Image, scale_factor: float) -> Template:
    scaled = image
    if scale_factor != 1.0:
        width = max(1, int(round(image.width * scale_factor)))
        height = max(1, int(round(image.height * scale_factor)))
        scaled = image.resize((width, height), Image.Resampling.BICUBIC)
    arr = np.asarray(scaled, dtype=np.uint8)
    mask = arr[:, :, 3] > 20
    if not mask.any():
        mask = np.ones(arr.shape[:2], dtype=bool)
    rgb = arr[:, :, :3].copy()
    return Template(
        name=name,
        path=path,
        rgb=rgb,
        mask=mask,
        anchors=choose_anchors(rgb, mask),
        scale=scale_factor,
    )


def load_templates(config: dict | None = None) -> dict[str, Template]:
    templates: dict[str, Template] = {}
    missing: list[Path] = []
    scale_values = template_scale_values(config)

    for name, filename in TEMPLATE_FILES.items():
        path = TEMPLATE_DIR / filename
        if not path.exists():
            missing.append(path)
            continue

        image = Image.open(path).convert("RGBA")
        primary = build_template(name, path, image, scale_values[0])
        variants = tuple(build_template(name, path, image, scale) for scale in scale_values[1:])
        templates[name] = Template(
            name=primary.name,
            path=primary.path,
            rgb=primary.rgb,
            mask=primary.mask,
            anchors=primary.anchors,
            scale=primary.scale,
            variants=variants,
        )

    if missing:
        joined = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"템플릿 파일이 없습니다:\n{joined}")

    return templates


def find_template_single(
    screen: ScreenShot,
    template: Template,
    tolerance: int,
    minimum_match: float,
    candidate_limit: int = 5000,
) -> Match | None:
    haystack = screen.rgb
    needle = template.rgb
    mask = template.mask
    th, tw = needle.shape[:2]
    sh, sw = haystack.shape[:2]

    if th > sh or tw > sw:
        return None

    search_h = sh - th + 1
    search_w = sw - tw + 1
    candidates: np.ndarray | None = None

    for anchor_y, anchor_x, color_tuple in template.anchors:
        color = np.asarray(color_tuple, dtype=np.int16)
        crop = haystack[anchor_y : anchor_y + search_h, anchor_x : anchor_x + search_w, :].astype(np.int16)
        anchor_match = np.max(np.abs(crop - color), axis=2) <= tolerance
        candidates = anchor_match if candidates is None else candidates & anchor_match
        if not candidates.any():
            return None

    ys, xs = np.nonzero(candidates)
    if len(xs) > candidate_limit:
        logging.debug("%s produced %d candidates; checking the first %d.", template.name, len(xs), candidate_limit)
        xs = xs[:candidate_limit]
        ys = ys[:candidate_limit]

    needle_i16 = needle.astype(np.int16)
    best: Match | None = None
    best_rank = -1.0

    for x, y in zip(xs, ys):
        window = haystack[y : y + th, x : x + tw, :].astype(np.int16)
        diffs = np.abs(window - needle_i16)
        masked_diffs = diffs[mask]
        if masked_diffs.size == 0:
            continue
        per_pixel_ok = np.max(masked_diffs, axis=1) <= tolerance
        score = float(per_pixel_ok.mean())
        mean_diff = float(masked_diffs.mean())
        rank = score - mean_diff / 1000.0
        if rank > best_rank:
            best_rank = rank
            best = Match(
                name=template.name,
                left=int(screen.origin_x + x),
                top=int(screen.origin_y + y),
                width=tw,
                height=th,
                score=score,
                mean_diff=mean_diff,
                scale=template.scale,
            )

    if not best:
        return None
    if best.score >= minimum_match:
        return best
    return None


def find_template(
    screen: ScreenShot,
    template: Template,
    tolerance: int,
    minimum_match: float,
    candidate_limit: int = 5000,
) -> Match | None:
    best: Match | None = None
    best_rank = -1.0
    for candidate in (template, *template.variants):
        match = find_template_single(screen, candidate, tolerance, minimum_match, candidate_limit)
        if not match:
            continue
        rank = match.score - match.mean_diff / 1000.0
        if rank > best_rank:
            best_rank = rank
            best = match
    return best


def find(
    name: str,
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
) -> Match | None:
    screen = capture_screen(region)
    match = find_template(screen, templates[name], tolerance, minimum_match)
    if match:
        logging.info(
            "found %-15s at (%d, %d) score=%.3f scale=%gx",
            name,
            match.center_x,
            match.center_y,
            match.score,
            match.scale,
        )
    else:
        logging.debug("not found %s", name)
    return match


def find_template_in_screen_region(
    screen: ScreenShot,
    template: Template,
    region: Region,
    tolerance: int,
    minimum_match: float,
) -> Match | None:
    left = max(region.left, screen.origin_x)
    top = max(region.top, screen.origin_y)
    right = min(region.right, screen.origin_x + screen.rgb.shape[1])
    bottom = min(region.bottom, screen.origin_y + screen.rgb.shape[0])
    if right <= left or bottom <= top:
        return None

    local_left = left - screen.origin_x
    local_top = top - screen.origin_y
    crop_rgb = screen.rgb[local_top : local_top + (bottom - top), local_left : local_left + (right - left), :]
    crop_screen = ScreenShot(Image.fromarray(crop_rgb, mode="RGB"), crop_rgb, left, top)
    return find_template(crop_screen, template, tolerance, minimum_match)


def wait_for(
    names: Iterable[str],
    templates: dict[str, Template],
    region: Region | None,
    tolerance: int,
    minimum_match: float,
    timeout_seconds: float,
    poll_seconds: float = 0.25,
) -> Match | None:
    deadline = time.monotonic() + timeout_seconds
    names = tuple(names)
    while time.monotonic() < deadline:
        screen = capture_screen(region)
        for name in names:
            match = find_template(screen, templates[name], tolerance, minimum_match)
            if match:
                logging.info(
                    "found %-15s at (%d, %d) score=%.3f scale=%gx",
                    name,
                    match.center_x,
                    match.center_y,
                    match.score,
                    match.scale,
                )
                return match
        time.sleep(poll_seconds)
    return None
