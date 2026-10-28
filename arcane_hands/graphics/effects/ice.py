"""Efek elemen es: Frost Nova, Ice Shards, dan Blizzard."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from arcane_hands.graphics.effects.base import Phase, SpellEffect, ease_out, pulse
from arcane_hands.graphics.palette import Color
from arcane_hands.graphics.particle import SHARD, SPARK
from arcane_hands.utils.geometry import angle_of, from_angle

TAU = math.tau
ICE = (Color.ICE_WHITE, Color.ICE_LIGHT, Color.ICE_CYAN)
SNOW = (Color.ICE_WHITE, Color.ICE_WHITE, Color.ICE_LIGHT, Color.ICE_CYAN)
ICE_POP = (Color.ICE_BLUE, Color.ICE_CYAN, Color.ICE_WHITE)


def _ice_orb(renderer, x: float, y: float, radius: float, intensity: float) -> None:
    renderer.orb(x, y, radius, Color.ICE_BLUE, Color.ICE_CYAN, Color.ICE_WHITE, intensity)


def _polygon_ring(renderer, x: float, y: float, radius: float, sides: int, rotation: float,
                  color: int, intensity: float) -> None:
    angles = rotation + np.arange(sides + 1) * (TAU / sides)
    pts = np.stack((x + np.cos(angles) * radius, y + np.sin(angles) * radius), axis=1)
    renderer.line(pts, color, 1, intensity)


@dataclass(slots=True)
class _Spike:
    angle: float
    length: float


class FrostNova(SpellEffect):
    """Telapak terbuka mengumpulkan es; mengepal melepaskan nova."""

    SPIKE_COUNT = 14
    SPIKE_TIME = 0.8

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.spikes: list[_Spike] = []
        self.spike_age = 0.0
        self.center = np.zeros(2, dtype=np.float32)

    def _radius(self) -> float:
        return (12.0 + 24.0 * self.energy) * self.cast.scale

    def on_charge(self, dt: float) -> None:
        p, c, e, radius = self.particles, self.cast.anchor, self.energy, self._radius()
        p.orbit(c, dt * (22 + 40 * e), radius=(radius * 1.6, radius * 2.4), omega=(2.5, 4.0),
                life=(0.5, 0.9), size=(7, 13), colors=ICE, kind=SHARD, spin=6.0)
        p.burst(c, dt * (30 + 40 * e), speed=(10, 50), life=(0.4, 0.8), size=(3, 6), colors=SNOW,
                kind=SPARK, jitter=radius * 1.5, gravity=30)

    def on_release(self) -> None:
        p, c, scale = self.particles, self.cast.anchor, self.cast.scale
        self.center = c.copy()
        p.burst(c, 46, speed=(150, 520), life=(0.5, 1.1), size=(10, 20), colors=ICE, kind=SHARD,
                drag=1.5, spin=8.0)
        p.burst(c, 40, speed=(100, 460), life=(0.5, 1.0), size=(3, 6), colors=SNOW, kind=SPARK, drag=1.2)
        self.add_ring(c, 20, 300 * scale, 0.7, Color.ICE_CYAN, 4)
        self.add_ring(c, 10, 220 * scale, 0.5, Color.ICE_WHITE, 2)
        self.add_ring(c, 20, 360 * scale, 0.9, Color.ICE_LIGHT, 2)
        self.add_pop(c, 120 * scale, 0.35, ICE_POP)
        rng = self.ctx.rng
        base = rng.uniform(0, TAU)
        self.spikes = [
            _Spike(base + i * TAU / self.SPIKE_COUNT + rng.uniform(-0.08, 0.08),
                   float(rng.uniform(90, 220)) * scale)
            for i in range(self.SPIKE_COUNT)
        ]
        self.spike_age = 0.0
        self.ctx.flash(0.3, (150, 210, 255))
        self.ctx.shake(4)
        self.fade = 0.0

    def on_update(self, dt: float) -> None:
        if self.spikes:
            self.spike_age += dt
            if self.spike_age > self.SPIKE_TIME:
                self.spikes = []

    def busy(self) -> bool:
        return bool(self.spikes)

    def paint(self, renderer) -> None:
        if self.fade > 0.0:
            c, radius = self.cast.anchor, self._radius()
            _ice_orb(renderer, c[0], c[1], radius, self.fade * pulse(self.time, 10))
            _polygon_ring(renderer, c[0], c[1], radius * 2.3, 6, self.time * 1.2, Color.ICE_LIGHT, 0.7 * self.fade)
            _polygon_ring(renderer, c[0], c[1], radius * 1.6, 6, -self.time * 1.8, Color.ICE_CYAN, 0.5 * self.fade)
        if self.spikes:
            self._paint_spikes(renderer)

    def _paint_spikes(self, renderer) -> None:
        cx, cy = self.center
        grow = ease_out(self.spike_age / 0.25)
        intensity = 1.0 - max(0.0, (self.spike_age - 0.35) / (self.SPIKE_TIME - 0.35))
        start = 30.0
        for spike in self.spikes:
            u = from_angle(spike.angle)
            n = np.array((-u[1], u[0]), dtype=np.float32)
            tip = np.array((cx, cy), dtype=np.float32) + u * (start + spike.length * grow)
            base = np.array((cx, cy), dtype=np.float32) + u * start
            renderer.polygon((tip, base + n * 7, base - n * 7), Color.ICE_LIGHT, 0.75 * intensity)
            renderer.line((base, tip), Color.ICE_WHITE, 1, intensity)


@dataclass(slots=True)
class _Shard:
    pos: np.ndarray
    vel: np.ndarray
    rot: float
    spin: float
    age: float = 0.0


class IceShards(SpellEffect):
    """Kristal berputar di telapak (pinch), dorong untuk melontarkannya sebagai kipas."""

    SPEED = 640.0
    EDGE_MARGIN = 16
    MAX_AGE = 2.0
    FAN = 0.14

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.flying: list[_Shard] = []

    def _count(self) -> int:
        return 3 + int(5 * self.energy)

    def _orbit_positions(self) -> list[np.ndarray]:
        n = self._count()
        radius = (34.0 + 10.0 * self.energy) * self.cast.scale
        base = self.time * 2.2
        return [self.cast.anchor + from_angle(base + k * TAU / n) * radius for k in range(n)]

    def on_charge(self, dt: float) -> None:
        p, c = self.particles, self.cast.anchor
        p.burst(c, dt * (30 + 50 * self.energy), speed=(10, 50), life=(0.4, 0.8), size=(3, 6), colors=SNOW,
                kind=SPARK, jitter=40 * self.cast.scale, gravity=20)

    def on_release(self) -> None:
        positions = self._orbit_positions()
        n = len(positions)
        aim_angle = angle_of(self.cast.aim)
        rng = self.ctx.rng
        for k, pos in enumerate(positions):
            direction = from_angle(aim_angle + (k - (n - 1) / 2) * self.FAN)
            self.flying.append(_Shard(pos.copy(), direction * (self.SPEED * float(rng.uniform(0.9, 1.1))),
                                      float(rng.uniform(0, TAU)), float(rng.uniform(-9, 9))))
        self.add_ring(self.cast.anchor, 20, 90, 0.3, Color.ICE_CYAN, 3)
        self.ctx.flash(0.15, (150, 210, 255))
        self.fade = 0.0

    def on_update(self, dt: float) -> None:
        p, trail = self.particles, self.ctx.quality.trail_scale
        survivors = []
        m = self.EDGE_MARGIN
        for shard in self.flying:
            shard.pos += shard.vel * dt
            shard.rot += shard.spin * dt
            shard.age += dt
            p.burst(shard.pos, dt * 70 * trail, speed=(5, 40), life=(0.25, 0.5), size=(3, 6), colors=SNOW,
                    kind=SPARK, inherit=-shard.vel * 0.05)
            x, y = shard.pos
            if shard.age > self.MAX_AGE or x < m or y < m or x > self.ctx.width - m or y > self.ctx.height - m:
                self._shatter(shard)
            else:
                survivors.append(shard)
        self.flying = survivors

    def _shatter(self, shard: _Shard) -> None:
        p = self.particles
        p.burst(shard.pos, 9, speed=(60, 260), life=(0.3, 0.7), size=(6, 12), colors=ICE, kind=SHARD,
                drag=1.5, spin=10.0)
        p.burst(shard.pos, 8, speed=(40, 200), life=(0.3, 0.6), size=(3, 5), colors=SNOW, kind=SPARK)
        self.add_ring(shard.pos, 4, 36, 0.25, Color.ICE_LIGHT, 2)

    def busy(self) -> bool:
        return bool(self.flying)

    def paint(self, renderer) -> None:
        if self.fade > 0.0 and self.phase is Phase.CHARGING:
            c = self.cast.anchor
            _ice_orb(renderer, c[0], c[1], 14.0 * self.cast.scale, self.fade * 0.8)
            size = (18.0 + 8.0 * self.energy) * self.cast.scale
            base = self.time * 2.2
            for k, pos in enumerate(self._orbit_positions()):
                angle = base + k * TAU / self._count() + math.pi / 2
                renderer.shard(pos[0], pos[1], size, size * 0.4, angle, Color.ICE_LIGHT, self.fade)
        for shard in self.flying:
            renderer.shard(shard.pos[0], shard.pos[1], 26.0 * self.cast.scale, 10.0 * self.cast.scale,
                           shard.rot, Color.ICE_LIGHT, 1.0)


class Blizzard(SpellEffect):
    """Gerakan melingkar memanggil pusaran salju dan kristal yang mengorbit pusat lingkaran."""

    def _tick(self, dt: float, level: float) -> None:
        p, c, s = self.particles, self.cast.anchor, self.cast.scale
        p.orbit(c, dt * 70 * level, radius=(15, 170 * s), omega=(1.8, 3.6), life=(0.7, 1.3), size=(4, 9),
                colors=SNOW, kind=SPARK)
        p.orbit(c, dt * 30 * level, radius=(20, 150 * s), omega=(1.5, 3.0), life=(0.8, 1.4), size=(5, 9),
                colors=SNOW, kind=SPARK, inward=0.7)
        p.orbit(c, dt * 22 * level, radius=(25, 160 * s), omega=(1.6, 3.2), life=(0.7, 1.2), size=(8, 14),
                colors=ICE, kind=SHARD, spin=5.0)

    def on_charge(self, dt: float) -> None:
        self._tick(dt, 0.4 + 0.6 * self.energy)

    def on_cast(self, dt: float) -> None:
        self._tick(dt, 1.0)

    def paint(self, renderer) -> None:
        if self.fade <= 0.0:
            return
        c, s = self.cast.anchor, self.cast.scale
        level = self.fade * (0.5 + 0.5 * min(1.0, self.energy))
        renderer.glow(c[0], c[1], 110 * s, Color.ICE_BLUE, 0.35 * level)
        theta = np.linspace(0.0, 4 * math.pi, 26)
        for arm in range(3):
            phase = self.time * 2.4 + arm * TAU / 3
            radius = (10.0 + theta * 12.0 * s) * (0.6 + 0.4 * level)
            pts = np.stack((c[0] + np.cos(theta + phase) * radius, c[1] + np.sin(theta + phase) * radius), axis=1)
            renderer.line(pts, Color.ICE_LIGHT, 2, 0.55 * level)
