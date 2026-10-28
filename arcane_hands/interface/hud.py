"""HUD bergaya dark fantasy yang digambar di atas jendela (resolusi asli, bukan render internal)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pygame

from arcane_hands.config import EFFECT_SCALE_RANGE, QUALITY_ORDER, SENSITIVITY_RANGE
from arcane_hands.interface.controls import KEY_HELP, Button, Command
from arcane_hands.spells.catalog import ELEMENTS, spells_for
from arcane_hands.spells.spell_manager import SpellState, SpellStatus

PANEL_BG = (12, 8, 22, 205)
PANEL_BORDER = (96, 66, 150)
TEXT = (226, 216, 242)
DIM = (150, 138, 176)
GOLD = (236, 196, 112)
GOOD = (120, 224, 150)
WARN = (244, 200, 90)
BAD = (240, 100, 96)
BUTTON_BG = (34, 24, 58)
BUTTON_ACTIVE = (88, 56, 150)

ELEMENT_COLORS = {
    "Fire": (255, 128, 48),
    "Ice": (110, 206, 255),
    "Lightning": (190, 200, 255),
    "Arcane": (190, 110, 255),
}
STATE_COLORS = {
    SpellState.IDLE: DIM,
    SpellState.CHARGING: WARN,
    SpellState.CASTING: GOOD,
    SpellState.COOLDOWN: (130, 160, 230),
    SpellState.DISSIPATING: (200, 140, 200),
}
TEXT_CACHE_LIMIT = 300
TOAST_SECONDS = 2.5
LEFT_W, RIGHT_W = 300, 276


@dataclass(slots=True)
class HudView:
    fps: float
    frame_ms: float
    particles: int
    particle_limit: int
    quality: str
    adaptive: bool
    sensitivity: float
    effect_scale: float
    element: str
    status: SpellStatus
    gesture_label: str
    webcam_status: str
    tracking_status: str
    fullscreen: bool
    camera_on: bool
    show_help: bool
    show_landmarks: bool
    hand_points: list = field(default_factory=list)  # titik (x, y) dalam koordinat render


class Hud:
    def __init__(self, window_size: tuple[int, int], to_window: Callable[[tuple[float, float]], tuple[int, int]]) -> None:
        if not pygame.font.get_init():
            pygame.font.init()
        self.buttons: list[Button] = []
        self._to_window = to_window
        self._text_cache: dict[tuple, pygame.Surface] = {}
        self._panels: dict[tuple[int, int], pygame.Surface] = {}
        self._toast = ""
        self._toast_left = 0.0
        self.resize(window_size)

    def resize(self, window_size: tuple[int, int]) -> None:
        self.size = window_size
        self.ui = max(0.75, min(window_size[0] / 1280, window_size[1] / 720))
        self.font = self._font(15)
        self.small = self._font(13)
        self.big = self._font(22, bold=True)
        self.title = self._font(17, bold=True)
        self._text_cache.clear()
        self._panels.clear()

    def _font(self, size: int, bold: bool = False) -> pygame.font.Font:
        return pygame.font.SysFont("segoeui,arial,dejavusans", round(size * self.ui), bold=bold)

    def notify(self, text: str) -> None:
        self._toast = text
        self._toast_left = TOAST_SECONDS

    def tick(self, dt: float) -> None:
        self._toast_left = max(0.0, self._toast_left - dt)

    def _text(self, font: pygame.font.Font, text: str, color: tuple[int, int, int]) -> pygame.Surface:
        key = (id(font), text, color)
        surface = self._text_cache.get(key)
        if surface is None:
            if len(self._text_cache) >= TEXT_CACHE_LIMIT:
                self._text_cache.clear()
            surface = font.render(text, True, color)
            self._text_cache[key] = surface
        return surface

    def _put(self, target, font, text, color, x: int, y: int, right: bool = False) -> int:
        surface = self._text(font, text, color)
        target.blit(surface, (x - surface.get_width() if right else x, y))
        return surface.get_height()

    def _panel(self, target, rect: pygame.Rect) -> None:
        key = (rect.w, rect.h)
        panel = self._panels.get(key)
        if panel is None:
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill(PANEL_BG)
            pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 1)
            self._panels[key] = panel
        target.blit(panel, rect.topleft)

    def _button(self, target, rect: pygame.Rect, label: str, command: Command, active: bool = False,
                accent: tuple[int, int, int] | None = None) -> None:
        pygame.draw.rect(target, BUTTON_ACTIVE if active else BUTTON_BG, rect)
        pygame.draw.rect(target, accent or PANEL_BORDER, rect, 2 if active else 1)
        surface = self._text(self.small, label, TEXT if active else DIM)
        target.blit(surface, surface.get_rect(center=rect.center))
        self.buttons.append(Button(rect, command))

    def _bar(self, target, rect: pygame.Rect, fraction: float, color: tuple[int, int, int]) -> None:
        pygame.draw.rect(target, (30, 22, 48), rect)
        fill = rect.copy()
        fill.w = round(rect.w * max(0.0, min(1.0, fraction)))
        if fill.w:
            pygame.draw.rect(target, color, fill)
        pygame.draw.rect(target, PANEL_BORDER, rect, 1)

    def draw(self, target: pygame.Surface, view: HudView) -> None:
        self.buttons = []
        self._draw_landmarks(target, view)
        self._draw_left(target, view)
        self._draw_right(target, view)
        if view.show_help:
            self._draw_help(target)
        self._draw_toast(target)

    def _draw_landmarks(self, target, view: HudView) -> None:
        if not view.show_landmarks:
            return
        for point in view.hand_points:
            x, y = self._to_window(point)
            pygame.draw.circle(target, (140, 255, 200), (x, y), max(2, round(3 * self.ui)))

    def _draw_left(self, target, view: HudView) -> None:
        u = self.ui
        pad = round(12 * u)
        rect = pygame.Rect(round(16 * u), round(16 * u), round(LEFT_W * u), round(384 * u))
        self._panel(target, rect)
        x, y = rect.x + pad, rect.y + pad
        y += self._put(target, self.title, "ARCANE HANDS", GOLD, x, y) + round(8 * u)

        gap = round(4 * u)
        bw = (rect.w - 2 * pad - 3 * gap) // 4
        bh = round(28 * u)
        for i, element in enumerate(ELEMENTS):
            button = pygame.Rect(x + i * (bw + gap), y, bw, bh)
            self._button(target, button, f"{i + 1} {element}", Command("element", element),
                         element == view.element, ELEMENT_COLORS[element])
        y += bh + round(10 * u)

        status = view.status
        accent = ELEMENT_COLORS[view.element]
        y += self._put(target, self.big, status.spell_name, accent, x, y) + round(2 * u)
        chip = status.state.value.upper()
        y += self._put(target, self.small, chip, STATE_COLORS[status.state], x, y) + round(8 * u)

        bar_w = rect.w - 2 * pad
        y += self._put(target, self.small, "Charge", DIM, x, y)
        self._bar(target, pygame.Rect(x, y, bar_w, round(10 * u)), status.charge, accent)
        y += round(18 * u)
        y += self._put(target, self.small, "Cooldown", DIM, x, y)
        self._bar(target, pygame.Rect(x, y, bar_w, round(10 * u)), status.cooldown, STATE_COLORS[SpellState.COOLDOWN])
        y += round(20 * u)

        y += self._put(target, self.small, "Gesture", DIM, x, y)
        y += self._put(target, self.font, view.gesture_label, TEXT, x, y) + round(6 * u)
        self._put(target, self.small, status.hint, DIM, x, y)

        # Daftar spell elemen aktif, spell yang sedang dipakai diberi tanda.
        y = rect.bottom - round(18 * u) - len(spells_for(view.element)) * round(17 * u)
        for spell in spells_for(view.element):
            active = status.spell_name == spell.name
            self._put(target, self.small, ("> " if active else "  ") + spell.name, accent if active else DIM, x, y)
            y += round(17 * u)

    def _draw_right(self, target, view: HudView) -> None:
        u = self.ui
        pad = round(12 * u)
        width = round(RIGHT_W * u)
        rect = pygame.Rect(self.size[0] - width - round(16 * u), round(16 * u), width, round(320 * u))
        self._panel(target, rect)
        x, y = rect.x + pad, rect.y + pad
        right = rect.right - pad

        fps_color = GOOD if view.fps >= 27 else WARN if view.fps >= 18 else BAD
        self._put(target, self.big, f"{view.fps:4.0f} FPS", fps_color, x, y)
        self._put(target, self.small, f"{view.frame_ms:4.1f} ms", DIM, right, y + round(6 * u), right=True)
        y += round(30 * u)
        y += self._put(target, self.small, f"Particles {view.particles} / {view.particle_limit}", TEXT, x, y)
        cam_color = GOOD if view.camera_on and view.webcam_status == "ok" else WARN
        track_color = GOOD if view.tracking_status == "ok" else WARN
        y += self._put(target, self.small, f"Webcam: {view.webcam_status}", cam_color, x, y)
        y += self._put(target, self.small, f"Tracking: {view.tracking_status}", track_color, x, y) + round(8 * u)

        gap = round(4 * u)
        bw = (rect.w - 2 * pad - 2 * gap) // 3
        bh = round(26 * u)
        for i, name in enumerate(QUALITY_ORDER):
            button = pygame.Rect(x + i * (bw + gap), y, bw, bh)
            self._button(target, button, name, Command("quality", name), name == view.quality)
        y += bh + gap
        wide = rect.w - 2 * pad
        self._button(target, pygame.Rect(x, y, wide, bh), f"Adaptive quality: {'ON' if view.adaptive else 'OFF'}",
                     Command("adaptive"), view.adaptive)
        y += bh + round(10 * u)

        y = self._stepper(target, x, y, wide, "Sensitivity", view.sensitivity, "sensitivity", SENSITIVITY_RANGE, view)
        y = self._stepper(target, x, y, wide, "Effect size", view.effect_scale, "effect_scale", EFFECT_SCALE_RANGE, view)
        half = (wide - gap) // 2
        self._button(target, pygame.Rect(x, y, half, bh), "Fullscreen" if not view.fullscreen else "Windowed",
                     Command("fullscreen"), view.fullscreen)
        self._button(target, pygame.Rect(x + half + gap, y, half, bh), "Webcam on" if view.camera_on else "Webcam off",
                     Command("camera"), view.camera_on)

    def _stepper(self, target, x: int, y: int, width: int, label: str, value: float, name: str,
                 bounds: tuple[float, float], view: HudView) -> int:
        u = self.ui
        size = round(24 * u)
        self._put(target, self.small, label, DIM, x, y + round(3 * u))
        plus = pygame.Rect(x + width - size, y, size, size)
        minus = pygame.Rect(plus.x - round(58 * u) - size, y, size, size)
        self._button(target, minus, "-", Command(name, -1), False)
        self._button(target, plus, "+", Command(name, 1), False)
        text = self._text(self.small, f"{value:.1f}", TEXT)
        target.blit(text, text.get_rect(center=((minus.right + plus.x) // 2, y + size // 2)))
        return y + size + round(6 * u)

    def _draw_help(self, target) -> None:
        u = self.ui
        parts = [f"{key}: {text}" for key, text in KEY_HELP]
        line = "   ".join(parts)
        surface = self._text(self.small, line, DIM)
        w, h = surface.get_size()
        rect = pygame.Rect(0, 0, w + round(24 * u), h + round(12 * u))
        rect.midbottom = (self.size[0] // 2, self.size[1] - round(10 * u))
        self._panel(target, rect)
        target.blit(surface, surface.get_rect(center=rect.center))

    def _draw_toast(self, target) -> None:
        if self._toast_left <= 0.0:
            return
        surface = self._text(self.font, self._toast, GOLD)
        target.blit(surface, surface.get_rect(midtop=(self.size[0] // 2, round(18 * self.ui))))
