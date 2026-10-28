"""Fungsi vektor 2D kecil yang dipakai bersama oleh gestur, spell, dan efek."""

from __future__ import annotations

import math

import numpy as np

DEFAULT_DIRECTION = (0.0, -1.0)


def unit(v, fallback=DEFAULT_DIRECTION) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float32)
    norm = float(math.hypot(arr[0], arr[1]))
    if norm < 1e-6:
        return np.array(fallback, dtype=np.float32)
    return arr / norm


def from_angle(angle: float) -> np.ndarray:
    return np.array((math.cos(angle), math.sin(angle)), dtype=np.float32)


def angle_of(v) -> float:
    return math.atan2(float(v[1]), float(v[0]))


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def jagged_path(start, end, rng: np.random.Generator, levels: int, roughness: float) -> np.ndarray:
    """Garis bergerigi dengan midpoint displacement; dipakai untuk petir dan busur energi."""
    pts = np.array((start, end), dtype=np.float32)
    delta = pts[1] - pts[0]
    length = float(math.hypot(delta[0], delta[1]))
    if length < 1.0:
        return pts
    normal = np.array((-delta[1], delta[0]), dtype=np.float32) / length
    sigma = length * roughness
    for _ in range(levels):
        mids = (pts[:-1] + pts[1:]) / 2
        mids += normal * rng.normal(0.0, sigma, len(mids)).astype(np.float32)[:, None]
        merged = np.empty((len(pts) + len(mids), 2), dtype=np.float32)
        merged[0::2] = pts
        merged[1::2] = mids
        pts = merged
        sigma *= 0.55
    return pts


def ray_to_bounds(origin, direction, width: float, height: float) -> float:
    """Jarak dari origin sepanjang direction sampai keluar dari kotak layar."""
    best = math.inf
    for o, d, limit in ((origin[0], direction[0], width), (origin[1], direction[1], height)):
        if d > 1e-6:
            best = min(best, (limit - o) / d)
        elif d < -1e-6:
            best = min(best, (0.0 - o) / d)
    return max(0.0, best) if best != math.inf else 0.0
