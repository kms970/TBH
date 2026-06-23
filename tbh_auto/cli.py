from __future__ import annotations

import argparse
import logging
import time

from .config import configure_logging, load_config
from .diagnostics import scan_templates
from .live_qa import run_settings_qa
from .state import set_active_config
from .vision import load_templates
from .windows import calibrate_region, enable_dpi_awareness, parse_region
from .workflow import run_once


def sleep_with_countdown(seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            break
        if remaining % 60 == 0 or remaining <= 10:
            logging.info("next run in %d seconds.", remaining)
        time.sleep(min(1, remaining))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task Bar Hero item auto-combine helper.")
    parser.add_argument("--once", action="store_true", help="Run one combine cycle and exit.")
    parser.add_argument("--scan", action="store_true", help="Only scan buttons and save logs/last_scan.png.")
    parser.add_argument("--calibrate", action="store_true", help="Save a screen search region to config.json.")
    parser.add_argument("--qa-settings", action="store_true", help="Run live QA for game window size and UI layout settings.")
    parser.add_argument("--region", help="Override search region: left,top,width,height.")
    parser.add_argument("--interval", type=int, help="Seconds between automatic runs.")
    parser.add_argument("--verbose", action="store_true", help="Print debug logs.")
    return parser


def main() -> int:
    enable_dpi_awareness()
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.verbose)
    config = load_config()

    if args.interval is not None:
        config["interval_seconds"] = args.interval

    if args.calibrate:
        calibrate_region(config)
        return 0

    region = parse_region(args.region, config)
    set_active_config(config)
    templates = load_templates(config)

    if args.scan:
        scan_templates(templates, region, config)
        return 0

    if args.qa_settings:
        return 0 if run_settings_qa(config) else 1

    if args.once:
        run_once(templates, region, config)
        return 0

    while True:
        run_once(templates, region, config)
        sleep_with_countdown(int(config["interval_seconds"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
