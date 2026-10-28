"""Penyimpanan partikel dalam bentuk array NumPy berkapasitas tetap (pool).

Partikel aktif selalu menempati indeks [0, count). Partikel yang mati dipadatkan
dengan masking sehingga tidak ada objek yang dibuat atau dibuang per partikel.
"""

from __future__ import annotations

import numpy as np

GLOW, SPARK, SHARD = 0, 1, 2
KIND_COUNT = 3

# Pengelompokan sprite agar jumlah surface yang di-cache tetap kecil.
SIZE_DIAMS = np.array([5, 9, 15, 24, 38, 60], dtype=np.float32)
SIZE_EDGES = (SIZE_DIAMS[:-1] + SIZE_DIAMS[1:]) / 2
SIZE_HALF = (SIZE_DIAMS / 2).astype(np.int32)
SIZE_BUCKETS = len(SIZE_DIAMS)
FADE_LEVELS = 6
ROT_BUCKETS = 8

_SCALAR_FIELDS = ("life", "max_life", "size0", "size1", "rot", "spin", "drag", "gravity", "attract", "swirl")


class ParticleBuffer:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity harus positif")
        self.capacity = capacity
        self.limit = capacity
        self.count = 0
        self.pos = np.zeros((capacity, 2), dtype=np.float32)
        self.vel = np.zeros((capacity, 2), dtype=np.float32)
        self.target = np.zeros((capacity, 2), dtype=np.float32)
        for name in _SCALAR_FIELDS:
            setattr(self, name, np.zeros(capacity, dtype=np.float32))
        self.color = np.zeros(capacity, dtype=np.int16)
        self.kind = np.zeros(capacity, dtype=np.uint8)
        names = ("pos", "vel", "target", *_SCALAR_FIELDS, "color", "kind")
        self._arrays = tuple(getattr(self, n) for n in names)

    @property
    def free(self) -> int:
        return max(0, self.limit - self.count)

    def add(self, n: int, *, pos, vel, target, life, size0, size1, rot, spin, drag, gravity,
            attract, swirl, color, kind) -> None:
        a, b = self.count, self.count + n
        self.pos[a:b] = pos
        self.vel[a:b] = vel
        self.target[a:b] = target
        self.life[a:b] = life
        self.max_life[a:b] = life
        self.size0[a:b] = size0
        self.size1[a:b] = size1
        self.rot[a:b] = rot
        self.spin[a:b] = spin
        self.drag[a:b] = drag
        self.gravity[a:b] = gravity
        self.attract[a:b] = attract
        self.swirl[a:b] = swirl
        self.color[a:b] = color
        self.kind[a:b] = kind
        self.count = b

    def compact(self, alive: np.ndarray) -> None:
        n = self.count
        k = int(alive.sum())
        if k == n:
            return
        for arr in self._arrays:
            arr[:k] = arr[:n][alive]
        self.count = k

    def set_limit(self, limit: int) -> None:
        self.limit = max(1, min(int(limit), self.capacity))
        if self.count > self.limit:
            # Pertahankan partikel yang masih paling lama hidup.
            keep = np.zeros(self.count, dtype=bool)
            keep[np.argsort(self.life[:self.count])[-self.limit:]] = True
            self.compact(keep)
