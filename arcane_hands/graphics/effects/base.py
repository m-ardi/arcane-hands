"""Kelas dasar efek spell.

Satu SpellEffect hidup dari charging sampai seluruh proyektil, cincin, dan pop-nya
selesai. SpellManager hanya mengatur fasenya; partikel milik ParticleSystem global.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable

import numpy as np

from arcane_hands.config import QualityPreset
from arcane_hands.graphics.particle_system import ParticleSystem


class Phase(Enum):
    CHARGING = auto()
    CASTING = auto()
    ENDING = auto()


def _zeros2() -> np.ndarray:
    return np.zeros(2, dtype=np.float32)


@dataclass(slots=True)
class CastInput:
    anchor: np.ndarray = field(default_factory=_zeros2)
    aim: np.ndarray = field(default_factory=lambda: np.array((0.0, -1.0), dtype=np.float32))
    energy: float = 0.0
    scale: float = 1.0
    hands: tuple[np.ndarray, np.ndarray] | None = None  # posisi kedua tangan untuk spell dua tangan


class EffectContext:
    """Sumber daya yang dibagikan ke semua efek."""

    def __init__(self, particles: ParticleSystem, bounds: tuple[int, int], quality: QualityPreset,
                 on_flash: Callable[[float, tuple[int, int, int]], None] | None = None,
                 on_shake: Callable[[float], None] | None = None) -> None:
        self.particles = particles
        self.width, self.height = bounds
        self.quality = quality
        self._on_flash = on_flash
        self._on_shake = on_shake

    @property
    def rng(self) -> np.random.Generator:
        return self.particles.rng

    def flash(self, strength: float, color: tuple[int, int, int] = (255, 255, 255)) -> None:
        if self._on_flash is not None and self.quality.screen_fx:
            self._on_flash(strength, color)

    def shake(self, amount: float) -> None:
        if self._on_shake is not None and self.quality.screen_fx:
            self._on_shake(amount)


@dataclass(slots=True)
class Ring:
    x: float
    y: float
    r0: float
    r1: float
    duration: float
    color: int
    width: int = 3
    age: float = 0.0


@dataclass(slots=True)
class Pop:
    """Kilatan glow singkat, misalnya pada titik ledakan."""
    x: float
    y: float
    radius: float
    duration: float
    colors: tuple[int, int, int]
    age: float = 0.0


class SpellEffect:
    ending_time = 0.4  # lama fade-out setelah kontrol dilepas

    def __init__(self, ctx: EffectContext) -> None:
        self.ctx = ctx
        self.particles = ctx.particles
        self.phase = Phase.CHARGING
        self.fade = 1.0
        self.time = 0.0
        self.cast = CastInput()
        self.energy = 0.0
        self.rings: list[Ring] = []
        self.pops: list[Pop] = []
        self.cancelled = False

    def update(self, dt: float, cast: CastInput | None = None) -> None:
        self.time += dt
        if cast is not None:
            self.cast = cast
            self.energy = cast.energy
        if self.phase is Phase.CHARGING:
            self.on_charge(dt)
        elif self.phase is Phase.CASTING:
            self.on_cast(dt)
        else:
            self.fade = max(0.0, self.fade - dt / self.ending_time)
        self.on_update(dt)
        self._tick_decor(dt)

    def release(self, cast: CastInput) -> None:
        self.cast = cast
        self.energy = cast.energy
        self.phase = Phase.CASTING
        self.on_release()

    def end(self) -> None:
        self.phase = Phase.ENDING

    def cancel(self) -> None:
        """Menghentikan efek seketika; partikel yang sudah ada mati secara alami."""
        self.cancelled = True

    @property
    def finished(self) -> bool:
        if self.cancelled:
            return True
        return (self.phase is Phase.ENDING and self.fade <= 0.0 and not self.rings
                and not self.pops and not self.busy())

    def busy(self) -> bool:
        """True bila masih ada proyektil atau elemen aktif lain di luar fase utama."""
        return False

    def on_charge(self, dt: float) -> None:
        pass

    def on_release(self) -> None:
        pass

    def on_cast(self, dt: float) -> None:
        pass

    def on_update(self, dt: float) -> None:
        pass

    def paint(self, renderer) -> None:
        pass

    def add_ring(self, pos, r0: float, r1: float, duration: float, color: int, width: int = 3) -> None:
        self.rings.append(Ring(float(pos[0]), float(pos[1]), r0, r1, duration, int(color), width))

    def add_pop(self, pos, radius: float, duration: float, colors: tuple[int, int, int]) -> None:
        self.pops.append(Pop(float(pos[0]), float(pos[1]), radius, duration, colors))

    def _tick_decor(self, dt: float) -> None:
        for item in self.rings:
            item.age += dt
        for item in self.pops:
            item.age += dt
        self.rings = [r for r in self.rings if r.age < r.duration]
        self.pops = [p for p in self.pops if p.age < p.duration]

    def draw(self, renderer) -> None:
        self.paint(renderer)
        for ring in self.rings:
            u = ring.age / ring.duration
            eased = 1.0 - (1.0 - u) ** 2
            renderer.ring(ring.x, ring.y, ring.r0 + (ring.r1 - ring.r0) * eased, ring.color,
                          1.0 - u, ring.width)
        for pop in self.pops:
            k = 1.0 - pop.age / pop.duration
            outer, inner, core = pop.colors
            renderer.orb(pop.x, pop.y, pop.radius * (0.6 + 0.4 * k), outer, inner, core, k)


def ease_out(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 1.0 - (1.0 - u) ** 2


def pulse(time: float, speed: float, low: float = 0.8, high: float = 1.0) -> float:
    return low + (high - low) * (0.5 + 0.5 * math.sin(time * speed))
