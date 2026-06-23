from __future__ import annotations

from PIL import ImageDraw

from .config import match_tolerance, minimum_match, reward_box_minimum_match
from .constants import REWARD_BOX_TEMPLATES
from .models import Region, Template
from .paths import LOG_DIR
from .vision import find_template, find_template_in_screen_region
from .windows import capture_screen
from .rewards import find_reward_bubble_by_shape
from .storage import (
    inventory_sort_search_region,
    storage_button_minimum,
    storage_button_tolerance,
)


def scan_templates(
    templates: dict[str, Template],
    region: Region | None,
    config: dict,
) -> None:
    default_tolerance = match_tolerance(config)
    default_minimum = minimum_match(config)
    screen = capture_screen(region)
    preview = screen.image.convert("RGB")
    draw = ImageDraw.Draw(preview)
    scan_transfer = None
    if "storage_to_bag" in templates:
        scan_transfer = find_template(
            screen,
            templates["storage_to_bag"],
            storage_button_tolerance(config),
            storage_button_minimum(config),
        )

    for name, template in templates.items():
        tolerance = default_tolerance
        minimum = default_minimum
        if name in REWARD_BOX_TEMPLATES:
            tolerance = max(tolerance, int(config.get("reward_box_match_tolerance", tolerance)))
            minimum = reward_box_minimum_match(config)
        elif name == "storage_to_bag":
            tolerance = storage_button_tolerance(config)
            minimum = storage_button_minimum(config)
        elif name == "cube_mode_option_combine":
            tolerance = max(tolerance, int(config.get("cube_mode_option_match_tolerance", 120)))
            minimum = min(minimum, float(config.get("cube_mode_option_minimum_match", 0.80)))
        elif name == "inventory_sort":
            tolerance = max(tolerance, int(config.get("inventory_sort_match_tolerance", tolerance)))
            minimum = min(minimum, float(config.get("inventory_sort_minimum_match", minimum)))

        if name == "inventory_sort" and scan_transfer:
            match = find_template_in_screen_region(
                screen,
                template,
                inventory_sort_search_region(scan_transfer, config),
                tolerance,
                minimum,
            )
        else:
            match = find_template(screen, template, tolerance, minimum)
            if not match and name in REWARD_BOX_TEMPLATES:
                match = find_reward_bubble_by_shape(screen, (name,), config)
        if match:
            print(
                f"{name:16} 인식됨 ({match.center_x}, {match.center_y}) "
                f"점수={match.score:.3f} 배율={match.scale:g}x 기준={minimum:.3f}/{tolerance}"
            )
            local_left = match.left - screen.origin_x
            local_top = match.top - screen.origin_y
            draw.rectangle(
                [local_left, local_top, local_left + match.width, local_top + match.height],
                outline=(255, 0, 0),
                width=2,
            )
            draw.text((local_left, max(0, local_top - 12)), name, fill=(255, 0, 0))
        else:
            print(f"{name:16} 인식 실패")

    LOG_DIR.mkdir(exist_ok=True)
    out_path = LOG_DIR / "last_scan.png"
    preview.save(out_path)
    print(f"검사 이미지 저장: {out_path}")
