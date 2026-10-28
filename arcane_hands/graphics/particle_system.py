"""Emisi, pembaruan, dan penggambaran partikel dengan operasi vektor NumPy."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from arcane_hands.config import QualityPreset
from arcane_hands.graphics.palette import PALETTE_SIZE
from arcane_hands.graphics.particle import (
    FADE_LEVELS,
    GLOW,
    ROT_BUCKETS,
    SHARD,
    SIZE_BUCKETS,
    SIZE_EDGES,
    SIZE_HALF,
    SPARK,
    ParticleBuffer,
)

TAU = math.tau
FADE_START = 0.45  # partikel mulai meredup pada sisa umur di bawah ini


class ParticleSystem:
    def __init__(self, capacity: int, rng: np.random.Generator | None = None) -> None:
        self.buf = ParticleBuffer(capacity)
        self.rng = rng if rng is not None else np.random.default_rng()
        self.density = 1.0

    @property
    def count(self) -> int:
        return self.buf.count

    @property
    def limit(self) -> int:
        return self.buf.limit

    def apply_quality(self, preset: QualityPreset) -> None:
        self.density = preset.density
        self.buf.set_limit(preset.max_particles)

    def clear(self) -> None:
        self.buf.count = 0

    def _claim(self, count: float) -> int:
        base = count * self.density
        n = int(base)
        if self.rng.random() < base - n:
            n += 1
        return min(n, self.buf.free)

    def _add(self, n, pos, vel, target, *, life, size, colors, kind, shrink, drag, gravity,
             spin, attract, swirl) -> None:
        rng = self.rng
        s0 = rng.uniform(size[0], size[1], n)
        self.buf.add(
            n,
            pos=pos,
            vel=vel,
            target=target,
            life=rng.uniform(life[0], life[1], n),
            size0=s0,
            size1=s0 * shrink,
            rot=rng.uniform(0.0, TAU, n),
            spin=rng.uniform(-spin, spin, n) if spin else 0.0,
            drag=drag,
            gravity=gravity,
            attract=attract,
            swirl=swirl,
            color=rng.choice(np.asarray(colors, dtype=np.int16), n),
            kind=kind,
        )

    def burst(self, origin, count: float, *, speed: tuple[float, float], life: tuple[float, float],
              size: tuple[float, float], colors: Sequence[int], angle: tuple[float, float] = (0.0, TAU),
              kind: int = GLOW, shrink: float = 0.2, drag: float = 0.0, gravity: float = 0.0,
              spin: float = 0.0, jitter: float = 0.0, inherit=None, attract: float = 0.0,
              swirl: float = 0.0, target=None) -> int:
        """Memancarkan partikel dari origin (titik atau array (m, 2)) ke arah acak dalam rentang angle."""
        origin = np.asarray(origin, dtype=np.float32)
        n = self._claim(count)
        if origin.ndim == 2:
            n = min(n, len(origin))
        if n <= 0:
            return 0
        rng = self.rng
        ang = rng.uniform(angle[0], angle[1], n)
        spd = rng.uniform(speed[0], speed[1], n)
        vel = np.empty((n, 2), dtype=np.float32)
        vel[:, 0] = np.cos(ang) * spd
        vel[:, 1] = np.sin(ang) * spd
        if inherit is not None:
            vel += np.asarray(inherit, dtype=np.float32)
        base = origin[:n] if origin.ndim == 2 else np.broadcast_to(origin, (n, 2))
        pos = base.astype(np.float32, copy=True)
        if jitter:
            pos += rng.normal(0.0, jitter, (n, 2)).astype(np.float32)
        tgt = pos if target is None else np.asarray(target, dtype=np.float32)
        self._add(n, pos, vel, tgt, life=life, size=size, colors=colors, kind=kind, shrink=shrink,
                  drag=drag, gravity=gravity, spin=spin, attract=attract, swirl=swirl)
        return n

    def orbit(self, center, count: float, *, radius: tuple[float, float], omega: tuple[float, float],
              life: tuple[float, float], size: tuple[float, float], colors: Sequence[int],
              kind: int = SPARK, direction: float = 1.0, inward: float = 1.0, shrink: float = 0.3,
              spin: float = 0.0, gravity: float = 0.0, drag: float = 0.0) -> int:
        """Partikel mengitari center. inward=1 menghasilkan orbit lingkaran; <1 melebar, >1 menyempit."""
        n = self._claim(count)
        if n <= 0:
            return 0
        rng = self.rng
        c = np.asarray(center, dtype=np.float32)
        ang = rng.uniform(0.0, TAU, n)
        r = rng.uniform(radius[0], radius[1], n)
        w = rng.uniform(omega[0], omega[1], n) * direction
        cos, sin = np.cos(ang), np.sin(ang)
        pos = np.stack((c[0] + cos * r, c[1] + sin * r), axis=1).astype(np.float32)
        vel = np.stack((-sin * w * r, cos * w * r), axis=1).astype(np.float32)
        self._add(n, pos, vel, np.broadcast_to(c, (n, 2)), life=life, size=size, colors=colors, kind=kind,
                  shrink=shrink, drag=drag, gravity=gravity, spin=spin, attract=w * w * r * inward, swirl=0.0)
        return n

    def gather(self, center, count: float, *, radius: tuple[float, float], accel: float,
               life: tuple[float, float], size: tuple[float, float], colors: Sequence[int],
               kind: int = SPARK, shrink: float = 0.3) -> int:
        """Partikel muncul di sekitar center lalu tertarik masuk."""
        n = self._claim(count)
        if n <= 0:
            return 0
        rng = self.rng
        c = np.asarray(center, dtype=np.float32)
        ang = rng.uniform(0.0, TAU, n)
        r = rng.uniform(radius[0], radius[1], n)
        pos = np.stack((c[0] + np.cos(ang) * r, c[1] + np.sin(ang) * r), axis=1).astype(np.float32)
        self._add(n, pos, np.zeros((n, 2), dtype=np.float32), np.broadcast_to(c, (n, 2)), life=life,
                  size=size, colors=colors, kind=kind, shrink=shrink, drag=0.0, gravity=0.0, spin=0.0,
                  attract=accel, swirl=0.0)
        return n

    def update(self, dt: float) -> None:
        b = self.buf
        n = b.count
        if n == 0:
            return
        pos, vel = b.pos[:n], b.vel[:n]
        attract, swirl = b.attract[:n], b.swirl[:n]
        if attract.any() or swirl.any():
            delta = b.target[:n] - pos
            dist = np.maximum(np.hypot(delta[:, 0], delta[:, 1]), 1.0)
            direction = delta / dist[:, None]
            vel += direction * (attract * dt)[:, None]
            vel[:, 0] -= direction[:, 1] * swirl * dt
            vel[:, 1] += direction[:, 0] * swirl * dt
        vel *= np.maximum(0.0, 1.0 - b.drag[:n] * dt)[:, None]
        vel[:, 1] += b.gravity[:n] * dt
        pos += vel * dt
        b.rot[:n] += b.spin[:n] * dt
        b.life[:n] -= dt
        alive = b.life[:n] > 0.0
        if not alive.all():
            b.compact(alive)

    def draw(self, target, sprites) -> None:
        """Menggambar semua partikel dengan blending aditif memakai sprite yang sudah di-cache."""
        b = self.buf
        n = b.count
        if n == 0:
            return
        life, max_life = b.life[:n], b.max_life[:n]
        t = life / max_life
        size = b.size1[:n] + (b.size0[:n] - b.size1[:n]) * t
        size_i = np.minimum(np.searchsorted(SIZE_EDGES, size), SIZE_BUCKETS - 1)
        bright = np.clip(t / FADE_START, 0.0, 1.0)
        fade_i = ((1.0 - bright) * (FADE_LEVELS - 1) + 0.5).astype(np.intp)
        kind = b.kind[:n].astype(np.intp)
        rot_i = ((b.rot[:n] % TAU) * (ROT_BUCKETS / TAU)).astype(np.intp) % ROT_BUCKETS
        rot_i = np.where(kind == SHARD, rot_i, 0)
        index = ((((kind * PALETTE_SIZE + b.color[:n]) * SIZE_BUCKETS + size_i) * FADE_LEVELS + fade_i)
                 * ROT_BUCKETS + rot_i)
        half = SIZE_HALF[size_i]
        xs = (b.pos[:n, 0] - half).astype(np.intp).tolist()
        ys = (b.pos[:n, 1] - half).astype(np.intp).tolist()
        flat, flag = sprites.flat, sprites.add_flag
        batch = []
        for i, x, y in zip(index.tolist(), xs, ys):
            entry = flat[i]
            if entry is None:
                entry = sprites.build(i)
            batch.append((entry[0], (x, y), entry[1], flag))
        target.blits(batch, False)
