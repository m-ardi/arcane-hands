import unittest

import numpy as np

from arcane_hands.config import QUALITY_PRESETS
from arcane_hands.graphics.palette import PALETTE_SIZE, Color
from arcane_hands.graphics.particle import (
    FADE_LEVELS,
    GLOW,
    KIND_COUNT,
    ROT_BUCKETS,
    SHARD,
    SIZE_BUCKETS,
    SPARK,
    ParticleBuffer,
)
from arcane_hands.graphics.particle_system import ParticleSystem

TOTAL_SPRITES = KIND_COUNT * PALETTE_SIZE * SIZE_BUCKETS * FADE_LEVELS * ROT_BUCKETS
BURST = dict(speed=(10, 50), life=(0.5, 1.0), size=(4, 20), colors=(Color.FIRE_ORANGE, Color.ICE_CYAN))


def make_system(limit: int, capacity: int = 1500) -> ParticleSystem:
    system = ParticleSystem(capacity, np.random.default_rng(1))
    system.apply_quality(QUALITY_PRESETS["HIGH"])
    system.buf.set_limit(limit)
    system.density = 1.0
    return system


class FakeSprites:
    add_flag = 0

    def __init__(self) -> None:
        self.flat = [None] * TOTAL_SPRITES
        self.built: list[int] = []

    def build(self, index: int):
        self.built.append(index)
        self.flat[index] = (object(), object())
        return self.flat[index]


class FakeTarget:
    def __init__(self) -> None:
        self.batches: list[list] = []

    def blits(self, batch, doreturn):
        self.batches.append(list(batch))


class LimitTests(unittest.TestCase):
    def test_burst_never_exceeds_limit(self):
        system = make_system(300)
        for _ in range(50):
            system.burst((100, 100), 40, **BURST)
        self.assertEqual(system.count, 300)

    def test_all_emitters_respect_the_limit(self):
        system = make_system(120)
        for _ in range(30):
            system.burst((100, 100), 30, **BURST)
            system.orbit((200, 200), 30, radius=(10, 50), omega=(2, 4), life=(0.5, 1.0), size=(3, 6),
                         colors=(Color.ARC_CYAN,))
            system.gather((300, 300), 30, radius=(50, 90), accel=300, life=(0.5, 1.0), size=(3, 6),
                          colors=(Color.ARC_PINK,))
        self.assertLessEqual(system.count, 120)

    def test_each_quality_preset_is_honoured(self):
        for name, preset in QUALITY_PRESETS.items():
            system = ParticleSystem(max(p.max_particles for p in QUALITY_PRESETS.values()), np.random.default_rng(2))
            system.apply_quality(preset)
            for _ in range(200):
                system.burst((0, 0), 50, **BURST)
            self.assertEqual(system.count, preset.max_particles, name)

    def test_lowering_quality_trims_existing_particles(self):
        system = ParticleSystem(1400, np.random.default_rng(3))
        system.apply_quality(QUALITY_PRESETS["HIGH"])
        for _ in range(100):
            system.burst((0, 0), 50, **BURST)
        self.assertGreater(system.count, QUALITY_PRESETS["LOW"].max_particles)
        system.apply_quality(QUALITY_PRESETS["LOW"])
        self.assertLessEqual(system.count, QUALITY_PRESETS["LOW"].max_particles)

    def test_density_scales_emission(self):
        low, high = make_system(1000), make_system(1000)
        low.density, high.density = 0.5, 1.0
        for system in (low, high):
            for _ in range(10):
                system.burst((0, 0), 10, **BURST)
        self.assertLess(low.count, high.count)

    def test_particles_expire_and_pool_empties(self):
        system = make_system(500)
        system.burst((0, 0), 200, **BURST)
        for _ in range(60):
            system.update(0.05)
        self.assertEqual(system.count, 0)

    def test_capacity_arrays_are_not_reallocated(self):
        system = make_system(400)
        pos_before = system.buf.pos
        for _ in range(30):
            system.burst((0, 0), 30, **BURST)
            system.update(0.03)
        self.assertIs(system.buf.pos, pos_before)
        self.assertEqual(system.buf.pos.shape[0], 1500)

    def test_buffer_rejects_invalid_capacity(self):
        with self.assertRaises(ValueError):
            ParticleBuffer(0)


class BehaviourTests(unittest.TestCase):
    def test_compaction_keeps_survivor_data_intact(self):
        system = make_system(100)
        system.burst((10, 10), 5, speed=(0, 0), life=(0.1, 0.1), size=(5, 5), colors=(Color.FIRE_RED,))
        system.burst((500, 400), 5, speed=(0, 0), life=(5.0, 5.0), size=(5, 5), colors=(Color.ICE_CYAN,))
        system.update(0.2)
        self.assertEqual(system.count, 5)
        self.assertTrue(np.allclose(system.buf.pos[:5], (500, 400)))
        self.assertTrue((system.buf.color[:5] == Color.ICE_CYAN).all())

    def test_gravity_pulls_down(self):
        system = make_system(100)
        system.burst((100, 100), 10, speed=(0, 0), life=(2, 2), size=(5, 5), colors=(Color.EMBER,), gravity=200)
        system.update(0.5)
        self.assertTrue((system.buf.pos[:system.count, 1] > 100).all())

    def test_orbit_particles_stay_near_their_circle(self):
        system = make_system(100)
        center = np.array((300.0, 300.0))
        system.orbit(center, 30, radius=(50, 50), omega=(3, 3), life=(3, 3), size=(4, 4), colors=(Color.ARC_CYAN,))
        for _ in range(60):
            system.update(1 / 60)
        offsets = np.hypot(*(system.buf.pos[:system.count] - center).T)
        self.assertTrue(((offsets > 35) & (offsets < 65)).all(), offsets)

    def test_gather_pulls_particles_inward(self):
        system = make_system(100)
        center = np.array((300.0, 300.0))
        system.gather(center, 20, radius=(100, 100), accel=600, life=(1, 1), size=(4, 4), colors=(Color.ARC_PINK,))
        start = np.hypot(*(system.buf.pos[:system.count] - center).T).mean()
        for _ in range(10):
            system.update(1 / 30)
        end = np.hypot(*(system.buf.pos[:system.count] - center).T).mean()
        self.assertLess(end, start)

    def test_clear_empties_pool(self):
        system = make_system(100)
        system.burst((0, 0), 50, **BURST)
        system.clear()
        self.assertEqual(system.count, 0)


class DrawTests(unittest.TestCase):
    def test_draw_uses_valid_sprite_indices_and_caches(self):
        system = make_system(600)
        sprites, target = FakeSprites(), FakeTarget()
        for kind in (GLOW, SPARK, SHARD):
            system.burst((200, 200), 60, kind=kind, spin=5.0, **BURST)
        system.draw(target, sprites)
        first_builds = len(sprites.built)
        self.assertEqual(len(target.batches[0]), system.count)
        self.assertTrue(all(0 <= i < TOTAL_SPRITES for i in sprites.built))
        system.draw(target, sprites)
        self.assertEqual(len(sprites.built), first_builds)

    def test_draw_with_no_particles_does_nothing(self):
        system = make_system(10)
        target = FakeTarget()
        system.draw(target, FakeSprites())
        self.assertEqual(target.batches, [])


if __name__ == "__main__":
    unittest.main()
