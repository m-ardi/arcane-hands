"""Mengatur siklus spell: idle -> charging -> casting -> cooldown / dissipating."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from arcane_hands.config import SENSITIVITY_RANGE, QualityPreset
from arcane_hands.gestures.gesture_controller import GestureFrame
from arcane_hands.graphics.effects.base import CastInput, EffectContext, SpellEffect
from arcane_hands.spells.catalog import (
    ELEMENTS,
    HAND_SIZE_REF,
    SPELL_BY_KEY,
    TWO_HANDS,
    Grip,
    SpellDef,
    spells_for,
)
from arcane_hands.utils.geometry import clamp, ray_to_bounds, unit

START_ENERGY = 0.15
CAST_HOLD = 0.3            # lama status CASTING setelah pelepasan
DISSIPATE_HOLD = 0.4
MIN_RELEASE_ENERGY = 0.3   # ambang untuk spell yang dilepas saat gestur berakhir
DEMO_CHARGE_TIME = 1.2
DEMO_CHANNEL_TIME = 2.6


class SpellState(Enum):
    IDLE = "idle"
    CHARGING = "charging"
    CASTING = "casting"
    COOLDOWN = "cooldown"
    DISSIPATING = "dissipating"


@dataclass(slots=True)
class Session:
    spell: SpellDef
    effect: SpellEffect
    slot: int | None
    grip: Grip
    energy: float = START_ENERGY
    age: float = 0.0
    lost_for: float = 0.0
    demo: bool = False


@dataclass(frozen=True)
class SpellStatus:
    state: SpellState
    spell_name: str
    charge: float
    cooldown: float   # 0..1, sisa cooldown
    hint: str


class SpellManager:
    def __init__(self, ctx: EffectContext, element: str = "Fire", effect_scale: float = 1.0,
                 sensitivity: float = 1.0) -> None:
        if element not in ELEMENTS:
            raise ValueError(f"Elemen tidak dikenal: {element!r}")
        self.ctx = ctx
        self.element = element
        self.effect_scale = effect_scale
        self.sensitivity = clamp(sensitivity, *SENSITIVITY_RANGE)
        self.effects: list[SpellEffect] = []
        self.session: Session | None = None
        self._tail: list[list] = []   # [[SpellState, sisa, total], ...]
        self._last_spell: SpellDef | None = None

    @property
    def max_effects(self) -> int:
        return self.ctx.quality.max_effects

    def set_quality(self, preset: QualityPreset) -> None:
        self.ctx.quality = preset

    def select_element(self, element: str) -> None:
        if element not in ELEMENTS:
            raise ValueError(f"Elemen tidak dikenal: {element!r}")
        if element != self.element:
            self.stop_session()
            self.element = element

    def cycle_element(self, step: int = 1) -> None:
        self.select_element(ELEMENTS[(ELEMENTS.index(self.element) + step) % len(ELEMENTS)])

    @property
    def state(self) -> SpellState:
        if self.session is not None:
            return self._session_state(self.session)
        return self._tail[0][0] if self._tail else SpellState.IDLE

    def _session_state(self, s: Session) -> SpellState:
        if s.spell.mode == "channel" and s.energy >= 1.0:
            return SpellState.CASTING
        return SpellState.CHARGING

    def status(self) -> SpellStatus:
        state = self.state
        spell = self.session.spell if self.session is not None else self._last_spell
        charge = self.session.energy if self.session is not None else 0.0
        cooldown = 0.0
        if self._tail and self._tail[0][0] is SpellState.COOLDOWN:
            _, left, total = self._tail[0]
            cooldown = left / total if total > 0 else 0.0
        if spell is not None:
            return SpellStatus(state, spell.name, charge, cooldown, spell.gesture)
        names = ", ".join(s.name for s in spells_for(self.element))
        return SpellStatus(state, "-", 0.0, 0.0, names)

    def update(self, frame: GestureFrame, dt: float) -> None:
        self._advance_tail(dt)
        session = self.session
        if session is not None:
            self._advance_session(session, frame, dt)
        elif not self._tail:
            self._try_start(frame)
        session = self.session
        for effect in self.effects:
            effect.update(dt, self._cast_of(session) if session and effect is session.effect else None)
        self.effects = [e for e in self.effects if not e.finished]

    def _advance_tail(self, dt: float) -> None:
        if not self._tail:
            return
        self._tail[0][1] -= dt
        if self._tail[0][1] <= 0.0:
            self._tail.pop(0)

    def _try_start(self, frame: GestureFrame) -> None:
        if len(self.effects) >= self.max_effects:
            return
        candidates = spells_for(self.element)
        two_handed = [s for s in candidates if s.hands == 2]
        for spell in two_handed + [s for s in candidates if s.hands == 1]:
            if spell.hands == 1 and any(s.arm is not None and s.arm(frame) for s in two_handed):
                return
            grip = spell.grip(frame, None)
            if grip is not None:
                self._begin(spell, grip, demo=False)
                return

    def _begin(self, spell: SpellDef, grip: Grip, demo: bool) -> None:
        effect = spell.effect(self.ctx)
        slot = grip.slot if grip.slot is not None else TWO_HANDS
        self.session = Session(spell, effect, slot, grip, demo=demo)
        self._last_spell = spell
        self.effects.append(effect)
        effect.cast = self._cast_of(self.session)

    def _cast_of(self, s: Session) -> CastInput:
        return CastInput(
            anchor=s.grip.anchor,
            aim=s.grip.aim,
            energy=s.energy,
            scale=clamp(s.grip.size / HAND_SIZE_REF, 0.7, 1.4) * self.effect_scale,
            hands=s.grip.hands,
        )

    def _advance_session(self, s: Session, frame: GestureFrame, dt: float) -> None:
        s.age += dt
        spell = s.spell
        if s.demo:
            self._advance_demo(s, dt)
            return
        aim = spell.fires(frame, s.slot) if spell.mode == "launch" and spell.fires else None
        grip = spell.grip(frame, s.slot)
        if aim is not None and s.age > 0.05:
            if grip is not None:
                s.grip = grip
            self._release(s, aim)
            return
        if grip is None:
            s.lost_for += dt
            if s.lost_for > spell.grace:
                self._lose(s, frame)
            return
        s.lost_for = 0.0
        s.grip = grip
        s.energy = min(1.0, s.energy + dt / spell.charge_time * self.sensitivity)

    def _advance_demo(self, s: Session, dt: float) -> None:
        s.energy = min(1.0, s.energy + dt / DEMO_CHARGE_TIME)
        if s.spell.mode == "launch" and s.age >= DEMO_CHARGE_TIME:
            self._release(s, s.grip.aim)
        elif s.spell.mode == "channel" and s.age >= DEMO_CHANNEL_TIME:
            self._finish(s, SpellState.DISSIPATING)

    def _lose(self, s: Session, frame: GestureFrame) -> None:
        hand_present = bool(frame.hands)
        if s.spell.release_on_lost and s.energy >= MIN_RELEASE_ENERGY and hand_present:
            self._release(s, s.grip.aim)
        else:
            self._finish(s, SpellState.DISSIPATING)

    def _release(self, s: Session, aim: np.ndarray) -> None:
        if s.spell.longer_side and s.grip.hands is not None:
            origin = s.grip.anchor
            forward = ray_to_bounds(origin, aim, self.ctx.width, self.ctx.height)
            backward = ray_to_bounds(origin, -aim, self.ctx.width, self.ctx.height)
            if backward > forward:
                aim = -aim
        s.grip.aim = unit(aim)
        s.effect.release(self._cast_of(s))
        s.effect.end()
        self._finish(s, SpellState.CASTING, ended=True)

    def _finish(self, s: Session, tail_state: SpellState, ended: bool = False) -> None:
        if not ended:
            s.effect.end()
        self.session = None
        cooldown = s.spell.cooldown
        if tail_state is SpellState.CASTING:
            self._tail = [[SpellState.CASTING, CAST_HOLD, CAST_HOLD], [SpellState.COOLDOWN, cooldown, cooldown]]
        else:
            self._tail = [[SpellState.DISSIPATING, DISSIPATE_HOLD, DISSIPATE_HOLD],
                          [SpellState.COOLDOWN, cooldown * 0.5, cooldown * 0.5]]

    def stop_session(self) -> None:
        if self.session is not None:
            self._finish(self.session, SpellState.DISSIPATING)

    def clear(self) -> None:
        self.session = None
        self._tail = []
        for effect in self.effects:
            effect.cancel()
        self.effects = []

    def demo_cast(self, key: str, anchor: tuple[float, float]) -> bool:
        """Tes tanpa webcam: spell berjalan sendiri dengan jangkar dan arah tetap."""
        spell = SPELL_BY_KEY.get(key)
        if spell is None or len(self.effects) >= self.max_effects:
            return False
        self.stop_session()
        self._tail = []
        origin = np.asarray(anchor, dtype=np.float32)
        far_x = self.ctx.width * (0.95 if origin[0] < self.ctx.width / 2 else 0.05)
        aim = unit(np.array((far_x, self.ctx.height * 0.3), dtype=np.float32) - origin)
        hands = None
        if spell.hands == 2:
            offset = np.array((70.0, 0.0), dtype=np.float32)
            hands = (origin - offset, origin + offset)
        self._begin(spell, Grip(origin, aim, None, hands), demo=True)
        return True
