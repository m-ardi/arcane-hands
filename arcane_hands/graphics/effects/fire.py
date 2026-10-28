"""Efek elemen api: Fireball, Flame Burst, dan Inferno."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from arcane_hands.graphics.effects.base import Phase, SpellEffect, pulse
from arcane_hands.graphics.palette import Color
from arcane_hands.graphics.particle import SPARK
from arcane_hands.utils.geometry import angle_of, jagged_path

FLAME = (Color.FIRE_ORANGE, Color.FIRE_ORANGE, Color.FIRE_RED, Color.FIRE_YELLOW)
CORE = (Color.FIRE_WHITE, Color.FIRE_YELLOW)
EMBERS = (Color.EMBER, Color.FIRE_YELLOW)
SMOKE = (Color.SMOKE,)
FIRE_POP = (Color.FIRE_RED, Color.FIRE_ORANGE, Color.FIRE_YELLOW)


def _fire_orb(renderer, x: float, y: float, radius: float, intensity: float) -> None:
    renderer.orb(x, y, radius, Color.FIRE_RED, Color.FIRE_ORANGE, Color.FIRE_YELLOW, intensity)
    renderer.glow(x, y, radius * 0.9, Color.FIRE_WHITE, intensity)


@dataclass(slots=True)
class _Shot:
    pos: np.ndarray
    vel: np.ndarray
    radius: float
    age: float = 0.0


class Fireball(SpellEffect):
    """Dikepal untuk mengumpulkan energi, didorong untuk meluncurkan."""

    MAX_AGE = 2.2
    EDGE_MARGIN = 24

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.shots: list[_Shot] = []

    def _radius(self) -> float:
        return (12.0 + 30.0 * self.energy) * self.cast.scale

    def on_charge(self, dt: float) -> None:
        p, c, e, radius = self.particles, self.cast.anchor, self.energy, self._radius()
        p.burst(c, dt * (35 + 70 * e), speed=(20, 60), life=(0.3, 0.6), size=(radius * 0.5, radius),
                colors=FLAME, angle=(-2.6, -0.55), jitter=radius * 0.5, gravity=-140, shrink=0.15)
        p.orbit(c, dt * (18 + 30 * e), radius=(radius * 1.5, radius * 2.3), omega=(5, 8), life=(0.4, 0.8),
                size=(3, 6), colors=EMBERS)

    def on_release(self) -> None:
        c = self.cast
        radius = self._radius()
        speed = 520.0 + 260.0 * self.energy
        self.shots.append(_Shot(c.anchor.copy(), c.aim * speed, radius))
        self.add_ring(c.anchor, radius, radius * 3.2, 0.3, Color.FIRE_YELLOW, 3)
        self.fade = 0.0

    def on_update(self, dt: float) -> None:
        for shot in self.shots:
            shot.pos += shot.vel * dt
            shot.age += dt
            self._emit_trail(shot, dt)
        survivors = []
        for shot in self.shots:
            if self._leaving(shot):
                self._explode(shot)
            else:
                survivors.append(shot)
        self.shots = survivors

    def _leaving(self, shot: _Shot) -> bool:
        m = self.EDGE_MARGIN
        x, y = shot.pos
        return (shot.age > self.MAX_AGE or x < m or y < m
                or x > self.ctx.width - m or y > self.ctx.height - m)

    def _emit_trail(self, shot: _Shot, dt: float) -> None:
        p, ts, r = self.particles, self.ctx.quality.trail_scale, shot.radius
        behind = shot.pos - shot.vel * dt * 0.5
        p.burst(behind, dt * 110 * ts, speed=(10, 70), life=(0.25, 0.55), size=(r * 0.9, r * 1.4),
                colors=FLAME, inherit=-shot.vel * 0.08, shrink=0.15)
        p.burst(behind, dt * 30 * ts, speed=(40, 160), life=(0.4, 0.9), size=(3, 6), colors=EMBERS,
                kind=SPARK, gravity=60, inherit=-shot.vel * 0.15)
        p.burst(behind, dt * 14 * ts, speed=(10, 40), life=(0.5, 0.9), size=(r * 1.2, r * 2.0),
                colors=SMOKE, shrink=1.8)

    def _explode(self, shot: _Shot) -> None:
        p, pos, r = self.particles, shot.pos, shot.radius
        p.burst(pos, 46, speed=(80, 420), life=(0.35, 0.9), size=(r * 0.8, r * 1.8), colors=FLAME,
                drag=2.0, shrink=0.1)
        p.burst(pos, 30, speed=(150, 520), life=(0.4, 1.0), size=(3, 6), colors=EMBERS, kind=SPARK,
                gravity=240, drag=0.8)
        p.burst(pos, 10, speed=(30, 160), life=(0.2, 0.4), size=(r * 1.2, r * 2.0), colors=CORE, shrink=0.1)
        p.burst(pos, 10, speed=(30, 120), life=(0.7, 1.2), size=(r * 2.0, r * 3.0), colors=SMOKE, shrink=1.6)
        self.add_ring(pos, r, r * 5, 0.45, Color.FIRE_ORANGE, 4)
        self.add_ring(pos, r * 0.5, r * 3, 0.3, Color.FIRE_YELLOW, 2)
        self.add_pop(pos, r * 3, 0.25, FIRE_POP)
        self.ctx.flash(0.35, (255, 180, 90))
        self.ctx.shake(5)

    def busy(self) -> bool:
        return bool(self.shots)

    def paint(self, renderer) -> None:
        if self.fade > 0.0:
            c, radius = self.cast.anchor, self._radius()
            _fire_orb(renderer, c[0], c[1], radius, self.fade * pulse(self.time, 18))
            u = (self.time * 1.6) % 1.0
            renderer.ring(c[0], c[1], radius * (3.2 - 2.0 * u), Color.FIRE_ORANGE, self.fade * u, 2)
        for shot in self.shots:
            _fire_orb(renderer, shot.pos[0], shot.pos[1], shot.radius * 1.1, 1.0)


class FlameBurst(SpellEffect):
    """Telapak terbuka siap, dorong untuk menyemburkan api berbentuk kerucut."""

    DURATION = 0.55
    SPREAD = 0.34

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.direction = np.array((0.0, -1.0), dtype=np.float32)
        self.burn = 0.0

    def on_charge(self, dt: float) -> None:
        p, c, e = self.particles, self.cast.anchor, self.energy
        radius = (8.0 + 14.0 * e) * self.cast.scale
        p.burst(c, dt * (30 + 50 * e), speed=(20, 60), life=(0.25, 0.5), size=(radius * 0.6, radius * 1.2),
                colors=FLAME, angle=(-2.4, -0.74), jitter=radius * 0.6, gravity=-150, shrink=0.15)

    def on_release(self) -> None:
        self.direction = self.cast.aim.copy()
        self.burn = self.DURATION
        self.add_ring(self.cast.anchor, 10, 70, 0.25, Color.FIRE_YELLOW, 3)
        self.ctx.flash(0.2, (255, 170, 80))
        self.ctx.shake(3)

    def on_update(self, dt: float) -> None:
        if self.burn <= 0.0:
            return
        self.burn -= dt
        k = max(0.0, self.burn / self.DURATION)
        p = self.particles
        origin = self.cast.anchor + self.direction * 18.0
        a = angle_of(self.direction)
        wide = (a - self.SPREAD, a + self.SPREAD)
        narrow = (a - 0.15, a + 0.15)
        p.burst(origin, dt * 320 * k, speed=(380, 720), life=(0.28, 0.6), size=(16, 38), colors=FLAME,
                angle=wide, shrink=0.12, drag=1.2)
        p.burst(origin, dt * 140 * k, speed=(300, 560), life=(0.18, 0.35), size=(10, 22), colors=CORE,
                angle=narrow, shrink=0.1)
        p.burst(origin, dt * 70 * k, speed=(200, 700), life=(0.5, 1.0), size=(3, 5), colors=EMBERS,
                kind=SPARK, angle=(a - 0.5, a + 0.5), gravity=120)
        p.burst(origin, dt * 40 * k, speed=(90, 220), life=(0.7, 1.2), size=(20, 34), colors=SMOKE,
                angle=(a - 0.5, a + 0.5), shrink=2.0)

    def busy(self) -> bool:
        return self.burn > 0.0

    def paint(self, renderer) -> None:
        c = self.cast.anchor
        if self.phase is Phase.CHARGING:
            radius = (8.0 + 14.0 * self.energy) * self.cast.scale
            _fire_orb(renderer, c[0], c[1], radius, self.fade * pulse(self.time, 16))
        elif self.burn > 0.0:
            k = self.burn / self.DURATION
            origin = c + self.direction * 18.0
            _fire_orb(renderer, origin[0], origin[1], 34.0 * self.cast.scale * (0.6 + 0.4 * k), k)


class Inferno(SpellEffect):
    """Dua tangan mengumpulkan api; tangan dibuka lebar untuk meledakkan cincin api."""

    def _radius(self) -> float:
        return (14.0 + 40.0 * self.energy) * self.cast.scale

    def on_charge(self, dt: float) -> None:
        p, mid, e, radius = self.particles, self.cast.anchor, self.energy, self._radius()
        p.orbit(mid, dt * (40 + 80 * e), radius=(radius * 1.2, radius * 2.6), omega=(5, 9), life=(0.4, 0.8),
                size=(4, 10), colors=FLAME, kind=SPARK)
        p.burst(mid, dt * (40 + 60 * e), speed=(15, 50), life=(0.3, 0.6), size=(radius * 0.5, radius * 1.0),
                colors=FLAME, angle=(-math.pi, 0.0), jitter=radius * 0.6, gravity=-120, shrink=0.15)

    def on_release(self) -> None:
        p, mid, r = self.particles, self.cast.anchor, self._radius()
        p.burst(mid, 90, speed=(200, 720), life=(0.4, 1.0), size=(18, 42), colors=FLAME, drag=1.8, shrink=0.1)
        p.burst(mid, 40, speed=(300, 800), life=(0.4, 1.1), size=(3, 6), colors=EMBERS, kind=SPARK,
                gravity=200, drag=0.6)
        # Kecepatan hampir seragam sehingga partikel membentuk cincin api yang menyebar.
        p.burst(mid, 60, speed=(520, 560), life=(0.5, 0.7), size=(10, 16),
                colors=(Color.FIRE_YELLOW, Color.FIRE_ORANGE), shrink=0.2, drag=1.2)
        self.add_ring(mid, r, 380, 0.7, Color.FIRE_ORANGE, 5)
        self.add_ring(mid, r * 0.5, 260, 0.5, Color.FIRE_YELLOW, 3)
        self.add_ring(mid, r, 460, 0.9, Color.FIRE_RED, 2)
        self.add_pop(mid, 150, 0.35, FIRE_POP)
        self.ctx.flash(0.6, (255, 170, 80))
        self.ctx.shake(9)
        self.fade = 0.0

    def paint(self, renderer) -> None:
        if self.fade <= 0.0:
            return
        mid, radius = self.cast.anchor, self._radius()
        i = self.fade * pulse(self.time, 20)
        _fire_orb(renderer, mid[0], mid[1], radius, i)
        if self.cast.hands is not None:
            rng = self.ctx.rng
            for hand in self.cast.hands:
                path = jagged_path(hand, mid, rng, 2, 0.12)
                renderer.line(path, Color.FIRE_ORANGE, 2, 0.7 * self.fade)
        u = (self.time * 1.4) % 1.0
        renderer.ring(mid[0], mid[1], radius * (3.4 - 2.2 * u), Color.FIRE_ORANGE, self.fade * u, 2)
