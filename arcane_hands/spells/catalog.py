"""Daftar spell dan aturan gestur masing-masing.

Aturan dibuat unik di dalam satu elemen, jadi satu gestur tidak pernah memicu
lebih dari satu spell. Setiap spell punya tiga hal:
- grip: apakah gestur penahannya sedang dilakukan, dan di mana jangkarnya;
- fires: pemicu pelepasan (dorong, buka tangan, dll.), bila spell bertipe launch;
- mode: launch (kumpulkan lalu lepas) atau channel (aktif selama gestur dipertahankan).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from arcane_hands.gestures.gesture_controller import GestureFrame, HandState, Pose
from arcane_hands.graphics.effects.arcane import ArcaneOrb, ArcaneVortex, EnergyBeam, MagicShield
from arcane_hands.graphics.effects.base import SpellEffect
from arcane_hands.graphics.effects.fire import FlameBurst, Fireball, Inferno
from arcane_hands.graphics.effects.ice import Blizzard, FrostNova, IceShards
from arcane_hands.graphics.effects.lightning import LightningBolt, ThunderStorm
from arcane_hands.utils.geometry import unit

ELEMENTS: tuple[str, ...] = ("Fire", "Ice", "Lightning", "Arcane")

MIN_POSE_TIME = 0.12  # pose harus stabil sebentar sebelum spell dimulai
MIN_TOGETHER_TIME = 0.25
TWO_HANDS = -1        # nilai slot untuk sesi dua tangan saat gestur dipertahankan
HAND_SIZE_REF = 90.0  # ukuran telapak (piksel render) yang dianggap skala 1.0


@dataclass(slots=True)
class Grip:
    anchor: np.ndarray
    aim: np.ndarray
    slot: int | None = None
    hands: tuple[np.ndarray, np.ndarray] | None = None
    size: float = HAND_SIZE_REF


GripRule = Callable[[GestureFrame, int | None], "Grip | None"]
FireRule = Callable[[GestureFrame, int | None], "np.ndarray | None"]


@dataclass(frozen=True)
class SpellDef:
    key: str
    name: str
    element: str
    effect: type[SpellEffect]
    mode: str                  # "launch" atau "channel"
    grip: GripRule
    gesture: str               # petunjuk singkat untuk HUD
    fires: FireRule | None = None
    hands: int = 1
    release_on_lost: bool = False
    arm: Callable[[GestureFrame], bool] | None = None  # spell dua tangan sedang bersiap; spell satu tangan menunggu
    charge_time: float = 1.4
    cooldown: float = 0.5
    grace: float = 0.3
    longer_side: bool = False  # arah dipilih ke sisi layar yang lebih panjang


def _held_pose(poses: tuple[Pose, ...], anchor: str, start: tuple[Pose, ...] | None = None) -> GripRule:
    """poses berlaku saat gestur dipertahankan; start (bila ada) membatasi pose untuk memulai."""
    start_poses = poses if start is None else start

    def rule(frame: GestureFrame, slot: int | None) -> Grip | None:
        for hand in frame.hands:
            if slot is not None and hand.slot != slot:
                continue
            allowed = poses if slot is not None else start_poses
            if hand.pose not in allowed or (slot is None and hand.pose_time < MIN_POSE_TIME):
                continue
            point = {"palm": hand.palm, "tip": hand.tip, "pinch": hand.pinch_point}[anchor]
            return Grip(point.copy(), hand.aim.copy(), hand.slot, size=hand.size)
        return None
    return rule


def _held_circle(poses: tuple[Pose, ...]) -> GripRule:
    def rule(frame: GestureFrame, slot: int | None) -> Grip | None:
        for hand in frame.hands:
            if slot is not None and hand.slot != slot:
                continue
            if hand.circling and hand.pose in poses:
                return Grip(hand.circle_center.copy(), hand.aim.copy(), hand.slot, size=hand.size)
        return None
    return rule


def _two_hands(condition: Callable[[GestureFrame], bool], need_time: float = 0.0) -> GripRule:
    def rule(frame: GestureFrame, slot: int | None) -> Grip | None:
        two = frame.two
        if two is None or not condition(frame):
            return None
        if slot is None and two.together_time < need_time:
            return None
        a, b = frame.hands
        axis = unit(b.palm - a.palm, (1.0, 0.0))
        return Grip(two.mid.copy(), axis, None, (a.palm.copy(), b.palm.copy()), (a.size + b.size) / 2)
    return rule


def _push(frame: GestureFrame, slot: int | None) -> np.ndarray | None:
    hand: HandState | None = frame.hand_by_slot(slot)
    return hand.push_dir.copy() if hand is not None and hand.push else None


def _fist_release(frame: GestureFrame, slot: int | None) -> np.ndarray | None:
    hand = frame.hand_by_slot(slot)
    return hand.aim.copy() if hand is not None and hand.pose is Pose.FIST else None


def _apart(frame: GestureFrame, slot: int | None) -> np.ndarray | None:
    two = frame.two
    if two is None or not two.apart_event:
        return None
    a, b = frame.hands
    return unit(b.palm - a.palm, (1.0, 0.0))


def _together(frame: GestureFrame) -> bool:
    return frame.two is not None and frame.two.near


def _bringing_together(frame: GestureFrame) -> bool:
    return frame.two is not None and frame.two.together


def _raised(frame: GestureFrame) -> bool:
    return frame.two is not None and frame.two.raised and frame.two.raised_time > 0.2


# Nova dimulai dari telapak terbuka, tetapi tetap dianggap dipegang saat jari
# melengkung ke arah kepalan sampai pose benar-benar menjadi FIST.
_NOVA_HOLD = (Pose.OPEN, Pose.UNKNOWN)

SPELLS: tuple[SpellDef, ...] = (
    SpellDef("fireball", "Fireball", "Fire", Fireball, "launch",
             _held_pose((Pose.FIST,), "palm"), "Fist: charge, then push", fires=_push, charge_time=1.5),
    SpellDef("flame_burst", "Flame Burst", "Fire", FlameBurst, "launch",
             _held_pose((Pose.OPEN,), "palm"), "Open palm: charge, then push", fires=_push, charge_time=0.8),
    SpellDef("inferno", "Inferno", "Fire", Inferno, "launch",
             _two_hands(_together, MIN_TOGETHER_TIME), "Two hands together, then pull apart",
             fires=_apart, hands=2, arm=_bringing_together, charge_time=1.8, cooldown=0.9),
    SpellDef("frost_nova", "Frost Nova", "Ice", FrostNova, "launch",
             _held_pose(_NOVA_HOLD, "palm", start=(Pose.OPEN,)), "Open palm: charge, then close to a fist",
             fires=_fist_release, charge_time=1.3, cooldown=0.8),
    SpellDef("ice_shards", "Ice Shards", "Ice", IceShards, "launch",
             _held_pose((Pose.PINCH,), "pinch"), "Pinch: gather crystals, then push",
             fires=_push, charge_time=1.2),
    SpellDef("blizzard", "Blizzard", "Ice", Blizzard, "channel",
             _held_circle((Pose.POINT, Pose.FIST)), "Point or fist: move hand in circles",
             charge_time=0.8, grace=0.5),
    SpellDef("lightning_bolt", "Lightning Bolt", "Lightning", LightningBolt, "channel",
             _held_pose((Pose.POINT,), "tip"), "Point your index finger", charge_time=0.4, grace=0.2),
    SpellDef("thunder_storm", "Thunder Storm", "Lightning", ThunderStorm, "channel",
             _two_hands(_raised), "Raise both open hands", hands=2, charge_time=0.5, grace=0.4, cooldown=0.8),
    SpellDef("arcane_orb", "Arcane Orb", "Arcane", ArcaneOrb, "launch",
             _held_pose((Pose.PINCH,), "pinch"), "Pinch: grow the orb, release to burst",
             release_on_lost=True, charge_time=1.6),
    SpellDef("magic_shield", "Magic Shield", "Arcane", MagicShield, "channel",
             _held_pose((Pose.OPEN,), "palm"), "Hold an open palm", charge_time=1.0, grace=0.35),
    SpellDef("energy_beam", "Energy Beam", "Arcane", EnergyBeam, "launch",
             _two_hands(_together, MIN_TOGETHER_TIME), "Two hands together, then pull apart",
             fires=_apart, hands=2, arm=_bringing_together, charge_time=1.6, cooldown=1.0, longer_side=True),
    SpellDef("arcane_vortex", "Arcane Vortex", "Arcane", ArcaneVortex, "channel",
             _held_circle((Pose.POINT, Pose.FIST)), "Point or fist: move hand in circles",
             charge_time=0.8, grace=0.5),
)

SPELL_BY_KEY: dict[str, SpellDef] = {s.key: s for s in SPELLS}


def spells_for(element: str) -> tuple[SpellDef, ...]:
    return tuple(s for s in SPELLS if s.element == element)


def validate_catalog() -> None:
    keys = [s.key for s in SPELLS]
    if len(set(keys)) != len(keys):
        raise ValueError("Kunci spell duplikat")
    for spell in SPELLS:
        if spell.element not in ELEMENTS:
            raise ValueError(f"Elemen {spell.element!r} tidak dikenal pada {spell.key}")
        if spell.mode == "launch" and spell.fires is None and not spell.release_on_lost:
            raise ValueError(f"Spell launch {spell.key} tidak punya pemicu pelepasan")
        if spell.mode not in ("launch", "channel"):
            raise ValueError(f"Mode {spell.mode!r} pada {spell.key} tidak valid")
