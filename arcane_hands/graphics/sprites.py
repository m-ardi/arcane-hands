"""Cache sprite glow dan partikel. Semua sprite dibuat sekali lalu dipakai ulang."""

from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np
import pygame

from arcane_hands.graphics.palette import PALETTE_RGB, PALETTE_SIZE
from arcane_hands.graphics.particle import (
    FADE_LEVELS,
    GLOW,
    KIND_COUNT,
    ROT_BUCKETS,
    SHARD,
    SIZE_BUCKETS,
    SIZE_DIAMS,
    SPARK,
)

FADE_VALUES = np.linspace(1.0, 0.12, FADE_LEVELS)
TOTAL_SPRITES = KIND_COUNT * PALETTE_SIZE * SIZE_BUCKETS * FADE_LEVELS * ROT_BUCKETS

GLOW_STEP = 6            # kelipatan radius (piksel) untuk glow besar
GLOW_MAX_STEPS = 22
GLOW_LEVELS = 4          # tingkat intensitas glow besar
GLOW_CACHE_LIMIT = 192   # membatasi memori glow besar


def _falloff(diameter: int, power: float) -> tuple[np.ndarray, np.ndarray]:
    axis = (np.arange(diameter, dtype=np.float32) - (diameter - 1) / 2) / (diameter / 2)
    radius = np.sqrt(axis[:, None] ** 2 + axis[None, :] ** 2)
    return np.clip(1.0 - radius, 0.0, 1.0) ** power, radius


def _to_surface(arr: np.ndarray) -> pygame.Surface:
    return pygame.surfarray.make_surface(np.clip(arr, 0, 255).astype(np.uint8)).convert()


def _entry(surface: pygame.Surface) -> tuple[pygame.Surface, pygame.Rect]:
    return surface, surface.get_rect()


def _particle_surface(kind: int, rgb: np.ndarray, intensity: float, diameter: int, rot: int) -> pygame.Surface:
    if kind == GLOW:
        falloff, _ = _falloff(diameter, 2.0)
        return _to_surface(falloff[..., None] * rgb * intensity)
    if kind == SPARK:
        falloff, radius = _falloff(diameter, 2.2)
        core = np.clip(1.0 - radius * 2.4, 0.0, 1.0) ** 1.5
        return _to_surface(falloff[..., None] * rgb * intensity + core[..., None] * 255.0 * 0.65 * intensity)
    falloff, _ = _falloff(diameter, 2.5)
    surface = _to_surface(falloff[..., None] * rgb * intensity * 0.4)
    angle = rot * math.tau / ROT_BUCKETS
    c = (diameter - 1) / 2
    half_len = diameter * 0.46
    half_wid = half_len * 0.28
    ux, uy = math.cos(angle), math.sin(angle)
    points = [
        (c + half_len * ux, c + half_len * uy),
        (c - half_wid * uy, c + half_wid * ux),
        (c - half_len * ux, c - half_len * uy),
        (c + half_wid * uy, c - half_wid * ux),
    ]
    fill = tuple(int(v) for v in (rgb + (255 - rgb) * 0.35) * intensity)
    points = [(round(x), round(y)) for x, y in points]
    pygame.draw.polygon(surface, fill, points)
    pygame.draw.line(surface, tuple(int(255 * intensity) for _ in range(3)), points[0], points[2])
    return surface


class SpriteCache:
    def __init__(self) -> None:
        self.add_flag = pygame.BLEND_ADD
        # Setiap entri adalah (surface, rect) agar blit batch tidak perlu membuat Rect baru.
        self.flat: list[tuple[pygame.Surface, pygame.Rect] | None] = [None] * TOTAL_SPRITES
        self._glows: OrderedDict[tuple[int, int, int], tuple[pygame.Surface, pygame.Rect]] = OrderedDict()

    def build(self, index: int) -> tuple[pygame.Surface, pygame.Rect]:
        rest = index
        rot = rest % ROT_BUCKETS
        rest //= ROT_BUCKETS
        fade = rest % FADE_LEVELS
        rest //= FADE_LEVELS
        size = rest % SIZE_BUCKETS
        rest //= SIZE_BUCKETS
        color = rest % PALETTE_SIZE
        kind = rest // PALETTE_SIZE
        rgb = np.array(PALETTE_RGB[color], dtype=np.float32)
        surface = _particle_surface(kind, rgb, float(FADE_VALUES[fade]), int(SIZE_DIAMS[size]), rot)
        entry = _entry(surface)
        self.flat[index] = entry
        return entry

    def warm(self) -> None:
        """Membuat sprite glow dan spark di awal agar tidak ada jeda saat efek pertama muncul."""
        for kind in (GLOW, SPARK):
            for color in range(PALETTE_SIZE):
                for size in range(SIZE_BUCKETS):
                    for fade in range(FADE_LEVELS):
                        index = ((((kind * PALETTE_SIZE + color) * SIZE_BUCKETS + size) * FADE_LEVELS + fade)
                                 * ROT_BUCKETS)
                        self.build(index)

    def glow(self, color: int, radius: float, intensity: float):
        steps = max(1, min(GLOW_MAX_STEPS, round(radius / GLOW_STEP)))
        level = round(min(1.0, max(0.0, intensity)) * GLOW_LEVELS)
        if level <= 0:
            return None
        key = (int(color), steps, level)
        entry = self._glows.get(key)
        if entry is not None:
            self._glows.move_to_end(key)
            return entry
        falloff, _ = _falloff(steps * GLOW_STEP * 2, 2.0)
        rgb = np.array(PALETTE_RGB[int(color)], dtype=np.float32)
        entry = _entry(_to_surface(falloff[..., None] * rgb * (level / GLOW_LEVELS)))
        self._glows[key] = entry
        if len(self._glows) > GLOW_CACHE_LIMIT:
            self._glows.popitem(last=False)
        return entry
