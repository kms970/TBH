from __future__ import annotations

CURRENT_CONFIG_VERSION = 6

DEFAULT_CONFIG = {
    "config_schema_version": CURRENT_CONFIG_VERSION,
    "interval_seconds": 1800,
    "search_region": None,
    "match_tolerance": 60,
    "minimum_match": 0.985,
    "scaled_match_tolerance": 80,
    "scaled_minimum_match": 0.975,
    "multi_scale_matching": True,
    "control_match_tolerance": 120,
    "control_minimum_match": 0.90,
    "click_delay_seconds": 0.25,
    "after_combine_delay_seconds": 2.5,
    "max_combines_per_run": 80,
    "no_progress_limit": 2,
    "game_screen_scale": "1x",
    "layout_independent_search": True,
    "reward_box_search_whole_region": True,
    "auto_follow_window": True,
    "search_region_follow_window": True,
    "search_region_from_window": None,
    "search_region_window_size": None,
    "bring_window_to_front": True,
    "prefer_print_window_capture": True,
    "print_window_capture_fallback": True,
    "window_title_keyword": "TaskBarHero",
    "window_region_padding": {"left": 0, "top": 0, "right": 0, "bottom": 0},
    "click_mode": "cursor",
    "cube_clear_attempts": 3,
    "back_offset_from_auto_fill": {"x": -11, "y": -50},
    "combine_button_offset_from_auto_fill": {"x": 137, "y": 0},
    "combine_button_search_radius": {"x": 62, "y": 28},
    "cube_slot_offsets_from_auto_fill": {
        "x": [24, 65, 106],
        "y": [-139, -98, -57],
    },
    "cube_slot_probe_size": 26,
    "cube_required_filled_slots": 9,
    "cube_slot_color_fraction": 0.05,
    "cube_slot_detail_fraction": 0.06,
    "cube_slot_luma_std": 22.0,
    "force_level_range_20_40": False,
    "target_level_range": "20_40",
    "locked_level_fallback": "lower",
    "open_reward_boxes_before_combine": True,
    "close_cube_before_reward_boxes": True,
    "cube_close_offset_from_level_button": {"x": 46, "y": -43},
    "cube_mode_option_match_tolerance": 120,
    "cube_mode_option_minimum_match": 0.80,
    "cube_mode_combine_option_offset_y": 29,
    "reward_box_max_opens": 60,
    "reward_box_max_clicks_by_type": {
        "reward_chest_bubble": 30,
        "reward_blue_box_bubble": 30,
    },
    "reward_box_same_position_limit": 30,
    "reward_box_same_position_bucket": 8,
    "reward_box_click_delay_seconds": 0.8,
    "reward_box_match_tolerance": 80,
    "reward_box_minimum_match": 0.94,
    "reward_box_effective_maximum_match": 0.94,
    "reward_box_context_validation": True,
    "reward_box_shape_fallback": True,
    "reward_box_shape_min_score": 0.62,
    "reward_box_row_tolerance": 32,
    "reward_box_pair_min_distance": 45,
    "reward_box_pair_max_distance": 140,
    "reward_box_search_area_from_region": {
        "left": 300,
        "top": 500,
        "width": 500,
        "height": 250,
    },
    "auto_fill_categories": ["equipment", "material"],
    "storage_transfer_max_page_attempts": 2,
    "storage_button_match_tolerance": 80,
    "storage_button_minimum_match": 0.90,
    "storage_page_offsets_from_transfer": [
        {"x": -130, "y": -342},
        {"x": -173, "y": -342},
    ],
    "inventory_sort_offset_from_transfer": {"x": 257, "y": -55},
    "inventory_sort_search_radius": 70,
    "inventory_sort_match_tolerance": 120,
    "inventory_sort_minimum_match": 0.90,
    "inventory_scroll_reset_enabled": True,
    "inventory_scroll_reset_wheel_notches": 8,
    "inventory_grid_from_transfer": {
        "left": 141,
        "top": -193,
        "cols": 7,
        "rows": 3,
        "pitch_x": 40,
        "pitch_y": 40,
        "slot_size": 35,
        "inner_margin": 5,
        "bright_fraction": 0.08,
        "saturation_fraction": 0.08,
        "std_threshold": 18.0,
    },
}

TEMPLATE_FILES = {
    "open_menu": "open_menu.png",
    "cube": "cube.png",
    "combine_tab": "combine_tab.png",
    "auto_fill": "auto_fill.png",
    "auto_fill_material": "auto_fill_material.png",
    "auto_fill_dropdown": "auto_fill_dropdown.png",
    "auto_fill_option_equipment": "auto_fill_option_equipment.png",
    "auto_fill_option_material": "auto_fill_option_material.png",
    "cube_mode_option_combine": "cube_mode_option_combine.png",
    "level_range_button_sample": "level_range_button_sample.png",
    "level_range_button_20_40": "level_range_button_20_40.png",
    "level_range_dropdown": "level_range_dropdown.png",
    "level_range_option_20_40": "level_range_option_20_40.png",
    "level_lock_icon": "level_lock_icon.png",
    "back": "back.png",
    "combine_ready": "combine_ready.png",
    "storage": "storage.png",
    "storage_to_bag": "storage_to_bag.png",
    "inventory_sort": "inventory_sort.png",
    "reward_chest_bubble": "reward_chest_bubble.png",
    "reward_blue_box_bubble": "reward_blue_box_bubble.png",
}

CATEGORY_OPTION_TEMPLATES = {
    "equipment": "auto_fill_option_equipment",
    "material": "auto_fill_option_material",
}

CATEGORY_LABELS = {
    "equipment": "장비",
    "material": "재료",
}

AUTO_FILL_BUTTON_TEMPLATES = ("auto_fill", "auto_fill_material")
REWARD_BOX_TEMPLATES = ("reward_chest_bubble", "reward_blue_box_bubble")

CATEGORY_OFFSETS_FROM_DROPDOWN = {
    "equipment": (-55, 32),
    "material": (-55, 59),
}

CATEGORY_OFFSETS_FROM_AUTOFILL = {
    "equipment": (13, 33),
    "material": (13, 60),
}

LEVEL_RANGE_CHOICES = {
    "1_10": {"label": "Lv.1~10", "offset_y": 28},
    "10_20": {"label": "Lv.10~20", "offset_y": 55},
    "15_30": {"label": "Lv.15~30", "offset_y": 81},
    "20_40": {"label": "Lv.20~40", "offset_y": 107},
    "30_50": {"label": "Lv.30~50", "offset_y": 134},
    "40_65": {"label": "Lv.40~65", "offset_y": 161},
    "50_65": {"label": "Lv.50~65", "offset_y": 188},
    "65_80": {"label": "Lv.65~80", "offset_y": 215},
}
LEVEL_RANGE_KEYS = tuple(LEVEL_RANGE_CHOICES.keys())

SCREEN_SCALE_CHOICES = {
    "1x": {"label": "1x", "factor": 1.0},
    "1.25x": {"label": "1.25x", "factor": 1.25},
    "1.5x": {"label": "1.5x", "factor": 1.5},
}
