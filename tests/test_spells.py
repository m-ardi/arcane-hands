import unittest

import numpy as np

from arcane_hands.config import QUALITY_PRESETS
from arcane_hands.gestures.gesture_controller import GestureFrame
from arcane_hands.graphics.effects.base import EffectContext
from arcane_hands.graphics.particle_system import ParticleSystem
from arcane_hands.spells.catalog import ELEMENTS, SPELLS, spells_for, validate_catalog
from arcane_hands.spells.spell_manager import SpellManager, SpellState
from tests.synthetic import DT, RENDER_SIZE, Rig, make_hand


class RecordingRenderer:
    """Meniru metode gambar Renderer dengan tanda tangan yang sama; hanya mencatat panggilan."""

    def __init__(self) -> None:
        self.calls = 0

    def glow(self, x, y, radius, color, intensity=1.0):
        self.calls += 1

    def orb(self, x, y, radius, outer, inner, core, intensity=1.0):
        self.calls += 1

    def ring(self, x, y, radius, color, intensity=1.0, width=2):
        self.calls += 1

    def line(self, points, color, width=1, intensity=1.0):
        assert len(points) >= 2
        self.calls += 1

    def polygon(self, points, color, intensity=1.0):
        self.calls += 1

    def shard(self, x, y, length, width, angle, color, intensity=1.0):
        self.calls += 1


class Harness:
    def __init__(self, quality: str = "LOW", element: str = "Fire") -> None:
        self.preset = QUALITY_PRESETS[quality]
        self.particles = ParticleSystem(1500, np.random.default_rng(7))
        self.particles.apply_quality(self.preset)
        self.flashes = 0
        self.ctx = EffectContext(self.particles, RENDER_SIZE, self.preset,
                                 on_flash=lambda *_: self._count(), on_shake=lambda *_: None)
        self.manager = SpellManager(self.ctx, element)
        self.renderer = RecordingRenderer()
        self.max_particles_seen = 0

    def _count(self) -> None:
        self.flashes += 1

    def step(self, frame: GestureFrame, dt: float = DT) -> None:
        self.manager.update(frame, dt)
        self.particles.update(dt)
        for effect in self.manager.effects:
            effect.draw(self.renderer)
        self.max_particles_seen = max(self.max_particles_seen, self.particles.count)

    def idle(self, seconds: float) -> None:
        for _ in range(round(seconds / DT)):
            self.step(GestureFrame())


class CatalogTests(unittest.TestCase):
    def test_catalog_is_valid(self):
        validate_catalog()

    def test_every_element_has_spells(self):
        for element in ELEMENTS:
            self.assertGreaterEqual(len(spells_for(element)), 2, element)

    def test_all_twelve_spells_from_the_brief_exist(self):
        names = {s.name for s in SPELLS}
        expected = {"Fireball", "Flame Burst", "Inferno", "Frost Nova", "Ice Shards", "Blizzard",
                    "Lightning Bolt", "Thunder Storm", "Arcane Orb", "Magic Shield", "Energy Beam",
                    "Arcane Vortex"}
        self.assertEqual(names, expected)


class GestureRoutingTests(unittest.TestCase):
    def test_no_hands_starts_nothing(self):
        h = Harness()
        h.idle(2.0)
        self.assertEqual(h.manager.state, SpellState.IDLE)
        self.assertEqual(h.manager.effects, [])

    def test_wrong_element_gesture_does_nothing(self):
        # Pinch adalah gestur Ice/Arcane; pada elemen Fire tidak boleh memicu apa pun.
        h, rig = Harness(element="Fire"), Rig()
        for _ in range(30):
            h.step(rig.step(make_hand("pinch")))
        self.assertIsNone(h.manager.session)

    def test_a_gesture_starts_only_one_spell(self):
        h, rig = Harness(element="Arcane"), Rig()
        for _ in range(30):
            h.step(rig.step(make_hand("pinch")))
        self.assertEqual(len(h.manager.effects), 1)
        self.assertEqual(h.manager.session.spell.name, "Arcane Orb")

    def test_switching_element_stops_active_spell(self):
        h, rig = Harness(element="Fire"), Rig()
        for _ in range(15):
            h.step(rig.step(make_hand("fist")))
        self.assertIsNotNone(h.manager.session)
        h.manager.select_element("Ice")
        self.assertIsNone(h.manager.session)

    def test_unknown_element_is_rejected(self):
        with self.assertRaises(ValueError):
            Harness().manager.select_element("Water")


class FireballLifecycleTests(unittest.TestCase):
    def _charged(self):
        h, rig = Harness(), Rig()
        for _ in range(45):
            h.step(rig.step(make_hand("fist", 300, 300)))
        return h, rig

    def test_fist_charges_fireball(self):
        h, _ = self._charged()
        status = h.manager.status()
        self.assertEqual(status.spell_name, "Fireball")
        self.assertEqual(status.state, SpellState.CHARGING)
        self.assertGreater(status.charge, 0.9)

    def test_charge_grows_over_time(self):
        h, rig = Harness(), Rig()
        samples = []
        for i in range(40):
            h.step(rig.step(make_hand("fist", 300, 300)))
            if i in (10, 39):
                samples.append(h.manager.status().charge)
        self.assertLess(samples[0], samples[1])

    def test_push_launches_and_projectile_travels_then_explodes(self):
        h, rig = self._charged()
        h.ctx.quality = QUALITY_PRESETS["MEDIUM"]  # flash layar hanya aktif di MEDIUM ke atas
        for i in range(1, 12):
            h.step(rig.step(make_hand("fist", 300 + 38 * i, 300)))
        effect = h.manager.effects[0]
        self.assertTrue(effect.shots, "proyektil harus ada setelah dorongan")
        x0 = effect.shots[0].pos[0]
        h.step(GestureFrame())
        self.assertGreater(effect.shots[0].pos[0], x0)
        peak_particles = 0
        for _ in range(90):
            h.step(GestureFrame())
            peak_particles = max(peak_particles, h.particles.count)
        self.assertEqual(effect.shots, [])
        self.assertGreater(peak_particles, 30, "ledakan harus menghasilkan banyak partikel")
        self.assertGreater(h.flashes, 0)

    def test_cooldown_blocks_immediate_recast(self):
        h, rig = self._charged()
        for i in range(1, 12):
            h.step(rig.step(make_hand("fist", 300 + 38 * i, 300)))
        self.assertIsNone(h.manager.session)
        states = set()
        for _ in range(6):
            h.step(rig.step(make_hand("fist", 700, 300)))
            states.add(h.manager.state)
            self.assertIsNone(h.manager.session)
        self.assertTrue(states & {SpellState.CASTING, SpellState.COOLDOWN})

    def test_losing_the_hand_dissipates_without_launching(self):
        h, _ = self._charged()
        for _ in range(30):
            h.step(GestureFrame())
        self.assertIsNone(h.manager.session)
        self.assertTrue(all(not getattr(e, "shots", []) for e in h.manager.effects))

    def test_lost_hand_does_not_start_new_spell(self):
        h, _ = self._charged()
        h.idle(3.0)
        h.idle(1.0)
        self.assertEqual(h.manager.state, SpellState.IDLE)

    def test_can_cast_again_after_cooldown(self):
        h, rig = self._charged()
        for i in range(1, 12):
            h.step(rig.step(make_hand("fist", 300 + 38 * i, 300)))
        h.idle(3.0)
        rig2 = Rig()
        for _ in range(20):
            h.step(rig2.step(make_hand("fist", 300, 300)))
        self.assertIsNotNone(h.manager.session)


class OtherSpellTests(unittest.TestCase):
    def test_pointing_casts_lightning_toward_the_finger(self):
        h, rig = Harness(element="Lightning"), Rig()
        for _ in range(20):
            h.step(rig.step(make_hand("point", 300, 400)))
        effect = h.manager.effects[0]
        self.assertEqual(h.manager.status().spell_name, "Lightning Bolt")
        self.assertGreater(effect.path[0][1] - effect.path[-1][1], 100, "petir harus mengarah ke atas")

    def test_lightning_shape_changes_over_time(self):
        h, rig = Harness(element="Lightning"), Rig()
        paths = []
        for i in range(30):
            h.step(rig.step(make_hand("point", 300, 400)))
            if i in (12, 29):
                paths.append(h.manager.effects[0].path.copy())
        self.assertFalse(len(paths[0]) == len(paths[1]) and np.allclose(paths[0], paths[1]))

    def test_raised_hands_call_thunder(self):
        h, rig = Harness(element="Lightning"), Rig()
        struck = False
        for _ in range(90):
            h.step(rig.step(make_hand("open", 300, 150), make_hand("open", 660, 150)))
            struck = struck or any(e.strikes for e in h.manager.effects)
        self.assertEqual(h.manager.status().spell_name, "Thunder Storm")
        self.assertTrue(struck, "harus ada sambaran petir")

    def test_two_hands_together_then_apart_fires_beam(self):
        h, rig = Harness(element="Arcane"), Rig()
        for _ in range(30):
            h.step(rig.step(make_hand("open", 400, 300), make_hand("open", 560, 300)))
        self.assertEqual(h.manager.status().spell_name, "Energy Beam")
        beam = None
        for i in range(1, 14):
            h.step(rig.step(make_hand("open", 400 - 18 * i, 300), make_hand("open", 560 + 18 * i, 300)))
            if h.manager.effects and getattr(h.manager.effects[0], "beam_left", 0) > 0:
                beam = h.manager.effects[0]
        self.assertIsNotNone(beam, "pancaran harus aktif setelah tangan dijauhkan")
        self.assertGreater(abs(beam.direction[0]), 0.9, "pancaran mengikuti sumbu kedua tangan")

    def test_two_open_palms_together_arm_beam_instead_of_shield(self):
        h, rig = Harness(element="Arcane"), Rig()
        for _ in range(8):
            h.step(rig.step(make_hand("open", 400, 300), make_hand("open", 560, 300)))
        self.assertIsNone(h.manager.session, "spell satu tangan harus menunggu saat dua tangan bersiap")

    def test_two_hands_together_arm_inferno_instead_of_flame_burst(self):
        h, rig = Harness(element="Fire"), Rig()
        for _ in range(30):
            h.step(rig.step(make_hand("open", 400, 300), make_hand("open", 560, 300)))
        self.assertEqual(h.manager.status().spell_name, "Inferno")

    def test_single_open_palm_still_holds_shield_when_other_hand_is_far(self):
        h, rig = Harness(element="Arcane"), Rig()
        for _ in range(30):
            h.step(rig.step(make_hand("open", 150, 300), make_hand("fist", 800, 300)))
        self.assertEqual(h.manager.status().spell_name, "Magic Shield")

    def test_open_palm_holds_shield(self):
        h, rig = Harness(element="Arcane"), Rig()
        for _ in range(40):
            h.step(rig.step(make_hand("open", 480, 300)))
        self.assertEqual(h.manager.status().spell_name, "Magic Shield")
        self.assertGreater(h.renderer.calls, 0)

    def test_circling_summons_blizzard(self):
        import math
        h, rig = Harness(element="Ice"), Rig()
        for i in range(90):
            a = i * DT * 5.5
            h.step(rig.step(make_hand("point", 480 + 70 * math.cos(a), 300 + 70 * math.sin(a))))
        self.assertEqual(h.manager.status().spell_name, "Blizzard")


class FullRunTests(unittest.TestCase):
    """Setiap spell dijalankan lewat demo pada setiap preset: harus selesai, tanpa error, dalam batas partikel."""

    def test_every_spell_runs_to_completion_on_every_preset(self):
        for quality, preset in QUALITY_PRESETS.items():
            for spell in SPELLS:
                with self.subTest(quality=quality, spell=spell.key):
                    h = Harness(quality, spell.element)
                    self.assertTrue(h.manager.demo_cast(spell.key, (RENDER_SIZE[0] * 0.4, RENDER_SIZE[1] * 0.6)))
                    for _ in range(round(12.0 / DT)):
                        h.step(GestureFrame())
                        if not h.manager.effects and h.particles.count == 0:
                            break
                    self.assertEqual(h.manager.effects, [], "efek harus selesai sendiri")
                    self.assertLessEqual(h.max_particles_seen, preset.max_particles)
                    self.assertGreater(h.renderer.calls, 0)

    def test_effect_count_is_capped_by_quality(self):
        h = Harness("LOW", "Fire")
        for _ in range(10):
            h.manager.demo_cast("flame_burst", (300, 300))
            h.step(GestureFrame())
        self.assertLessEqual(len(h.manager.effects), QUALITY_PRESETS["LOW"].max_effects)

    def test_clear_cancels_everything(self):
        h = Harness("HIGH", "Fire")
        h.manager.demo_cast("inferno", (300, 300))
        h.idle(1.5)
        h.manager.clear()
        self.assertEqual(h.manager.effects, [])
        self.assertEqual(h.manager.state, SpellState.IDLE)

    def test_sensitivity_speeds_up_charging(self):
        charges = []
        for sensitivity in (0.5, 2.0):
            h, rig = Harness(), Rig()
            h.manager.sensitivity = sensitivity
            for _ in range(20):
                h.step(rig.step(make_hand("fist", 300, 300)))
            charges.append(h.manager.status().charge)
        self.assertLess(charges[0], charges[1])


if __name__ == "__main__":
    unittest.main()
