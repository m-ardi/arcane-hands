"""Efek elemen arcane: Arcane Orb, Magic Shield, Energy Beam, dan Arcane Vortex."""

from __future__ import annotations

import math

import numpy as np

from arcane_hands.graphics.effects.base import Phase, SpellEffect, ease_out, pulse
from arcane_hands.graphics.palette import Color
from arcane_hands.graphics.particle import SPARK
from arcane_hands.utils.geometry import angle_of, from_angle, jagged_path, ray_to_bounds

TAU = math.tau
MOTES = (Color.ARC_PURPLE, Color.ARC_CYAN, Color.ARC_PINK, Color.ARC_VIOLET)
BRIGHT = (Color.ARC_WHITE, Color.ARC_CYAN, Color.ARC_PINK)
ARC_POP = (Color.ARC_VIOLET, Color.ARC_PURPLE, Color.ARC_WHITE)


def _arc_orb(renderer, x: float, y: float, radius: float, intensity: float) -> None:
    renderer.orb(x, y, radius, Color.ARC_VIOLET, Color.ARC_PURPLE, Color.ARC_CYAN, intensity)
    renderer.glow(x, y, radius * 0.7, Color.ARC_WHITE, intensity)


def _ring_dashed(renderer, x: float, y: float, radius: float, segments: int, phase: float,
                 color: int, intensity: float) -> None:
    """Cincin putus-putus; membuat cincin tampak berputar dan lebih menyerupai lingkaran sihir."""
    step = TAU / segments
    for k in range(0, segments, 2):
        a0, a1 = phase + k * step, phase + (k + 1) * step
        theta = np.linspace(a0, a1, 4)
        pts = np.stack((x + np.cos(theta) * radius, y + np.sin(theta) * radius), axis=1)
        renderer.line(pts, color, 2, intensity)


class ArcaneOrb(SpellEffect):
    """Kedua tangan mendekat mengumpulkan bola; menjauh menghilangkannya."""

    def _radius(self) -> float:
        return (16.0 + 34.0 * self.energy) * self.cast.scale

    def on_charge(self, dt: float) -> None:
        p, c, e, radius = self.particles, self.cast.anchor, self.energy, self._radius()
        p.orbit(c, dt * (35 + 60 * e), radius=(radius * 1.5, radius * 2.8), omega=(2.0, 5.0), life=(0.5, 1.0),
                size=(4, 9), colors=MOTES, kind=SPARK)
        p.gather(c, dt * (20 + 30 * e), radius=(radius * 3.0, radius * 4.0), accel=380, life=(0.4, 0.7),
                 size=(3, 6), colors=BRIGHT)

    def on_release(self) -> None:
        c, radius = self.cast.anchor, self._radius()
        self.particles.burst(c, 40, speed=(60, 340), life=(0.4, 0.9), size=(4, 9), colors=MOTES, kind=SPARK,
                             drag=1.4)
        self.add_ring(c, radius, radius * 4.5, 0.55, Color.ARC_CYAN, 3)
        self.add_pop(c, radius * 2.4, 0.3, ARC_POP)
        self.ctx.flash(0.2, (190, 140, 255))
        self.fade = 0.0

    def paint(self, renderer) -> None:
        if self.fade <= 0.0:
            return
        c, radius, f = self.cast.anchor, self._radius(), self.fade
        _arc_orb(renderer, c[0], c[1], radius, f * pulse(self.time, 9))
        renderer.ring(c[0], c[1], radius * 1.9, Color.ARC_PURPLE, 0.8 * f, 2)
        _ring_dashed(renderer, c[0], c[1], radius * 2.4, 10, self.time * 2.2, Color.ARC_CYAN, 0.9 * f)
        _ring_dashed(renderer, c[0], c[1], radius * 3.0, 14, -self.time * 1.3, Color.ARC_PINK, 0.6 * f)
        if self.cast.hands is not None:
            rng = self.ctx.rng
            for hand in self.cast.hands:
                renderer.line(jagged_path(hand, c, rng, 2, 0.08), Color.ARC_CYAN, 1, 0.5 * f)


class MagicShield(SpellEffect):
    """Telapak terbuka menahan perisai berisi cincin, rune sederhana, dan partikel orbit."""

    ending_time = 0.35
    RUNES = 8
    ROTATIONS = 6

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.grow = 0.0

    def _radius(self) -> float:
        return (70.0 + 50.0 * self.energy) * self.cast.scale * ease_out(self.grow)

    def on_charge(self, dt: float) -> None:
        self.grow = min(1.0, self.grow + dt / 0.35)
        self._emit(dt)

    def on_cast(self, dt: float) -> None:
        self.on_charge(dt)

    def _emit(self, dt: float) -> None:
        p, c, radius = self.particles, self.cast.anchor, self._radius()
        if radius < 8:
            return
        p.orbit(c, dt * 38, radius=(radius * 0.92, radius * 1.05), omega=(1.1, 1.7), life=(0.6, 1.0),
                size=(4, 8), colors=MOTES, kind=SPARK)
        p.orbit(c, dt * 20, radius=(radius * 0.7, radius * 0.8), omega=(1.8, 2.4), life=(0.5, 0.9),
                size=(3, 6), colors=BRIGHT, kind=SPARK, direction=-1.0)

    def on_update(self, dt: float) -> None:
        if self.phase is Phase.ENDING:
            self.grow = max(0.0, self.grow - dt / 0.35)

    def _rune(self, renderer, x: float, y: float, size: float, angle: float, kind: int, intensity: float) -> None:
        """Rune sederhana: segitiga, belah ketupat, atau garis bersilang."""
        if kind == 0:
            offsets = (angle, angle + TAU / 3, angle + 2 * TAU / 3, angle)
            pts = [(x + math.cos(a) * size, y + math.sin(a) * size) for a in offsets]
            renderer.line(pts, Color.ARC_CYAN, 2, intensity)
        elif kind == 1:
            offsets = [angle + k * math.pi / 2 for k in range(5)]
            pts = [(x + math.cos(a) * size, y + math.sin(a) * size * 0.65) for a in offsets]
            renderer.line(pts, Color.ARC_PINK, 2, intensity)
        else:
            for a in (angle, angle + math.pi / 2):
                d = from_angle(a) * size
                renderer.line(((x - d[0], y - d[1]), (x + d[0], y + d[1])), Color.ARC_WHITE, 2, intensity)

    def paint(self, renderer) -> None:
        radius = self._radius()
        if radius < 6 or self.fade <= 0.0:
            return
        c, f, t = self.cast.anchor, self.fade, self.time
        renderer.glow(c[0], c[1], radius * 1.25, Color.ARC_VIOLET, 0.55 * f * pulse(t, 5, 0.8, 1.0))
        renderer.ring(c[0], c[1], radius, Color.ARC_CYAN, 0.95 * f, 3)
        renderer.ring(c[0], c[1], radius * 0.78, Color.ARC_PURPLE, 0.8 * f, 2)
        _ring_dashed(renderer, c[0], c[1], radius * 0.88, 16, t * 0.9, Color.ARC_PINK, 0.7 * f)
        for k in range(self.RUNES):
            angle = t * 0.6 + k * TAU / self.RUNES
            pos = c + from_angle(angle) * radius * 0.89
            self._rune(renderer, pos[0], pos[1], radius * 0.07, angle + math.pi / 2, k % 3, 0.9 * f)
        hexagon = t * -0.5 + np.arange(self.ROTATIONS + 1) * (TAU / self.ROTATIONS)
        pts = np.stack((c[0] + np.cos(hexagon) * radius * 0.6, c[1] + np.sin(hexagon) * radius * 0.6), axis=1)
        renderer.line(pts, Color.ARC_CYAN, 1, 0.55 * f)


class EnergyBeam(SpellEffect):
    """Dua tangan mendekat mengumpulkan energi; menjauh melepas pancaran sepanjang sumbu tangan."""

    BEAM_TIME = 1.0
    ending_time = 0.1

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.beam_left = 0.0
        self.origin = np.zeros(2, dtype=np.float32)
        self.direction = np.array((1.0, 0.0), dtype=np.float32)
        self.length = 0.0

    def _radius(self) -> float:
        return (12.0 + 30.0 * self.energy) * self.cast.scale

    def on_charge(self, dt: float) -> None:
        p, c, e, radius = self.particles, self.cast.anchor, self.energy, self._radius()
        p.gather(c, dt * (50 + 60 * e), radius=(radius * 3.0, radius * 4.5), accel=500, life=(0.35, 0.6),
                 size=(3, 7), colors=BRIGHT)
        p.orbit(c, dt * (20 + 30 * e), radius=(radius * 1.2, radius * 2.0), omega=(5, 8), life=(0.3, 0.6),
                size=(4, 8), colors=MOTES, kind=SPARK)

    def on_release(self) -> None:
        c = self.cast
        self.origin = c.anchor.copy()
        self.direction = c.aim.copy()
        self.length = ray_to_bounds(self.origin, self.direction, self.ctx.width, self.ctx.height)
        self.beam_left = self.BEAM_TIME
        self.add_ring(self.origin, 10, 120, 0.3, Color.ARC_CYAN, 3)
        self.add_pop(self.origin, 70 * c.scale, 0.3, ARC_POP)
        self.ctx.flash(0.4, (170, 130, 255))
        self.ctx.shake(6)

    def on_update(self, dt: float) -> None:
        if self.beam_left <= 0.0:
            return
        self.beam_left -= dt
        k = max(0.0, self.beam_left / self.BEAM_TIME)
        p, a = self.particles, angle_of(self.direction)
        along = self.origin + self.direction * (self.length * float(self.ctx.rng.random()))
        p.burst(along, dt * 160 * k, speed=(30, 160), life=(0.2, 0.45), size=(3, 6), colors=BRIGHT, kind=SPARK,
                angle=(a + math.pi / 2 - 0.5, a + math.pi / 2 + 0.5))
        end = self.origin + self.direction * self.length
        p.burst(end, dt * 120 * k, speed=(80, 360), life=(0.2, 0.5), size=(3, 6), colors=BRIGHT, kind=SPARK)
        if k < 0.2:
            self.beam_left = min(self.beam_left, 0.2 * self.BEAM_TIME)

    def busy(self) -> bool:
        return self.beam_left > 0.0

    def paint(self, renderer) -> None:
        if self.phase is Phase.CHARGING:
            c, radius = self.cast.anchor, self._radius()
            _arc_orb(renderer, c[0], c[1], radius, self.fade * pulse(self.time, 14))
            if self.cast.hands is not None:
                for hand in self.cast.hands:
                    renderer.line((hand, c), Color.ARC_CYAN, 1, 0.5 * self.fade)
            return
        if self.beam_left <= 0.0:
            return
        k = self.beam_left / self.BEAM_TIME
        grow = ease_out((self.BEAM_TIME - self.beam_left) / 0.12)
        end = self.origin + self.direction * (self.length * grow)
        width = (10.0 + 22.0 * self.energy) * self.cast.scale * (0.5 + 0.5 * k)
        n = np.array((-self.direction[1], self.direction[0]), dtype=np.float32)
        for scale, color, intensity in ((1.0, Color.ARC_VIOLET, 0.45), (0.65, Color.ARC_CYAN, 0.75), (0.3, Color.ARC_WHITE, 1.0)):
            half = width * scale * 0.5 * (1.0 + 0.1 * math.sin(self.time * 60))
            renderer.polygon((self.origin + n * half, end + n * half * 0.6, end - n * half * 0.6, self.origin - n * half),
                             color, intensity * k)
        renderer.glow(self.origin[0], self.origin[1], width * 2.4, Color.ARC_CYAN, k)
        renderer.glow(end[0], end[1], width * 1.6, Color.ARC_WHITE, 0.8 * k)


class ArcaneVortex(SpellEffect):
    """Gerakan memutar membuka pusaran: partikel berspiral masuk menuju pusat."""

    def _tick(self, dt: float, level: float) -> None:
        p, c, s = self.particles, self.cast.anchor, self.cast.scale
        p.orbit(c, dt * 80 * level, radius=(40 * s, 190 * s), omega=(1.8, 3.2), life=(0.8, 1.4), size=(4, 9),
                colors=MOTES, kind=SPARK, inward=1.6)
        p.gather(c, dt * 40 * level, radius=(150 * s, 210 * s), accel=260, life=(0.6, 1.0), size=(3, 6),
                 colors=BRIGHT)

    def on_charge(self, dt: float) -> None:
        self._tick(dt, 0.4 + 0.6 * self.energy)

    def on_cast(self, dt: float) -> None:
        self._tick(dt, 1.0)

    def paint(self, renderer) -> None:
        if self.fade <= 0.0:
            return
        c, s = self.cast.anchor, self.cast.scale
        level = self.fade * (0.5 + 0.5 * min(1.0, self.energy))
        _arc_orb(renderer, c[0], c[1], 14 * s, level * pulse(self.time, 11))
        theta = np.linspace(0.0, 3.5 * math.pi, 28)
        for arm in range(4):
            phase = -self.time * 3.0 + arm * TAU / 4
            radius = (190.0 * s) * (1.0 - theta / (3.5 * math.pi)) ** 1.2 * (0.6 + 0.4 * level)
            pts = np.stack((c[0] + np.cos(theta + phase) * radius, c[1] + np.sin(theta + phase) * radius), axis=1)
            renderer.line(pts, Color.ARC_PURPLE if arm % 2 else Color.ARC_CYAN, 2, 0.6 * level)
