from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_bbox(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    @classmethod
    def from_config(cls, value: object) -> "Region | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("search_region must be null or an object.")
        return cls(
            left=int(value["left"]),
            top=int(value["top"]),
            width=int(value["width"]),
            height=int(value["height"]),
        )

    def to_config(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class ScreenShot:
    image: Image.Image
    rgb: np.ndarray
    origin_x: int
    origin_y: int


@dataclass(frozen=True)
class Match:
    name: str
    left: int
    top: int
    width: int
    height: int
    score: float
    mean_diff: float
    scale: float = 1.0

    @property
    def center_x(self) -> int:
        return self.left + self.width // 2

    @property
    def center_y(self) -> int:
        return self.top + self.height // 2


@dataclass(frozen=True)
class Template:
    name: str
    path: Path
    rgb: np.ndarray
    mask: np.ndarray
    anchors: tuple[tuple[int, int, tuple[int, int, int]], ...]
    scale: float = 1.0
    variants: tuple["Template", ...] = ()

    @property
    def width(self) -> int:
        return int(self.rgb.shape[1])

    @property
    def height(self) -> int:
        return int(self.rgb.shape[0])
