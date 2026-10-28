"""Efek elemen petir: Lightning Bolt dan Thunder Storm."""

from __future__ import annotations

import math

import numpy as np

from arcane_hands.graphics.effects.base import Phase, SpellEffect, pulse
from arcane_hands.graphics.palette import Color
from arcane_hands.graphics.particle import SPARK
from arcane_hands.utils.geometry import angle_of, from_angle, jagged_path, ray_to_bounds

SPARKS = (Color.BOLT_WHITE, Color.BOLT_BLUE, Color.ARC_CYAN)
BOLT_POP = (Color.BOLT_BLUE, Color.BOLT_BLUE, Color.BOLT_WHITE)
RESHAPE_INTERVAL = 0.06


def draw_bolt(renderer, path: np.ndarray, intensity: float, width: int = 3) -> None:
    """Petir tiga lapis: selubung biru lebar, lapisan tengah, dan inti putih tipis."""
    renderer.line(path, Color.BOLT_BLUE, width + 4, 0.35 * intensity)
    renderer.line(path, Color.BOLT_BLUE, width + 1, 0.8 * intensity)
    renderer.line(path, Color.BOLT_WHITE, max(1, width - 1), intensity)


def _branches(origin: np.ndarray, end: np.ndarray, path: np.ndarray, rng: np.random.Generator,
              count: int, levels: int) -> list[np.ndarray]:
    """Cabang pendek yang keluar dari titik acak pada jalur utama."""
    if len(path) < 6:
        return []
    forward = end - origin
    angle = angle_of(forward)
    total = float(math.hypot(forward[0], forward[1]))
    result = []
    for _ in range(count):
        i = int(rng.integers(2, len(path) - 2))
        side = float(rng.choice((-1.0, 1.0)))
        tilt = side * float(rng.uniform(0.4, 0.9))
        tip = path[i] + from_angle(angle + tilt) * total * float(rng.uniform(0.12, 0.28))
        result.append(jagged_path(path[i], tip, rng, max(1, levels - 1), 0.14))
    return result


class LightningBolt(SpellEffect):
    """Telunjuk menunjuk: petir bercabang menuju arah jari, bentuknya diacak berkala."""

    BRANCHES = 3

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.path = np.zeros((2, 2), dtype=np.float32)
        self.branches: list[np.ndarray] = []
        self.reshape_in = 0.0
        self.impact = np.zeros(2, dtype=np.float32)

    def _reshape(self) -> None:
        c, rng = self.cast, self.ctx.rng
        length = min(ray_to_bounds(c.anchor, c.aim, self.ctx.width, self.ctx.height), 620.0 * c.scale + 200.0)
        length = max(length, 40.0)
        end = c.anchor + c.aim * length
        levels = self.ctx.quality.bolt_levels
        self.path = jagged_path(c.anchor, end, rng, levels, 0.07)
        self.branches = _branches(c.anchor, end, self.path, rng, self.BRANCHES, levels)
        self.impact = end

    def on_charge(self, dt: float) -> None:
        self.reshape_in -= dt
        if self.reshape_in <= 0.0:
            self.reshape_in = RESHAPE_INTERVAL + float(self.ctx.rng.uniform(0.0, 0.04))
            self._reshape()
        p = self.particles
        p.burst(self.cast.anchor, dt * 50, speed=(60, 260), life=(0.12, 0.3), size=(3, 6), colors=SPARKS,
                kind=SPARK)
        p.burst(self.impact, dt * 30, speed=(80, 300), life=(0.15, 0.35), size=(3, 6), colors=SPARKS,
                kind=SPARK)

    def busy(self) -> bool:
        return False

    def paint(self, renderer) -> None:
        if self.fade <= 0.0 or self.phase is not Phase.CHARGING and self.phase is not Phase.ENDING:
            return
        c = self.cast.anchor
        i = self.fade * pulse(self.time, 60, 0.7, 1.0)
        renderer.glow(c[0], c[1], 40 * self.cast.scale, Color.BOLT_BLUE, 0.8 * i)
        renderer.glow(c[0], c[1], 18 * self.cast.scale, Color.BOLT_WHITE, i)
        draw_bolt(renderer, self.path, i, 3)
        for branch in self.branches:
            draw_bolt(renderer, branch, 0.7 * i, 2)
        renderer.glow(self.impact[0], self.impact[1], 28 * self.cast.scale, Color.BOLT_WHITE, 0.8 * i)


class ThunderStorm(SpellEffect):
    """Kedua tangan diangkat: sambaran petir singkat dari atas layar."""

    STRIKE_LIFE = 0.16

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.strikes: list[tuple[np.ndarray, list[np.ndarray], float]] = []
        self.next_strike = 0.0

    def _strike(self) -> None:
        rng, w, h = self.ctx.rng, self.ctx.width, self.ctx.height
        hands = self.cast.hands
        if hands is not None and rng.random() < 0.6:
            x = float(hands[int(rng.integers(0, 2))][0]) + float(rng.uniform(-60, 60))
        else:
            x = float(rng.uniform(0.1, 0.9)) * w
        x = min(max(x, 20.0), w - 20.0)
        top = np.array((x + float(rng.uniform(-30, 30)), -10.0), dtype=np.float32)
        ground = np.array((x, float(rng.uniform(0.55, 0.9)) * h), dtype=np.float32)
        levels = self.ctx.quality.bolt_levels
        path = jagged_path(top, ground, rng, levels, 0.09)
        branches = _branches(top, ground, path, rng, 3, levels)
        self.strikes.append((path, branches, self.STRIKE_LIFE))
        p = self.particles
        p.burst(ground, 20, speed=(60, 360), life=(0.2, 0.5), size=(3, 6), colors=SPARKS, kind=SPARK,
                gravity=300, angle=(-math.pi, 0.0))
        self.add_pop(ground, 55, 0.2, BOLT_POP)
        self.add_ring(ground, 6, 70, 0.25, Color.BOLT_BLUE, 2)
        self.ctx.flash(0.45, (190, 210, 255))
        self.ctx.shake(5)

    def on_charge(self, dt: float) -> None:
        self.next_strike -= dt
        if self.next_strike <= 0.0:
            self.next_strike = float(self.ctx.rng.uniform(0.28, 0.55))
            self._strike()
            if self.ctx.rng.random() < 0.35:
                self._strike()

    def on_update(self, dt: float) -> None:
        self.strikes = [(p, b, life - dt) for p, b, life in self.strikes if life - dt > 0.0]

    def busy(self) -> bool:
        return bool(self.strikes)

    def paint(self, renderer) -> None:
        for path, branches, life in self.strikes:
            k = life / self.STRIKE_LIFE
            draw_bolt(renderer, path, k, 4)
            for branch in branches:
                draw_bolt(renderer, branch, 0.7 * k, 2)
            renderer.glow(path[0][0], 0, 60, Color.BOLT_BLUE, 0.5 * k)
