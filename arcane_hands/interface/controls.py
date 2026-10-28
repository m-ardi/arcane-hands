"""Perintah pengguna dari keyboard dan klik mouse pada tombol HUD."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pygame

from arcane_hands.spells.catalog import ELEMENTS


@dataclass(frozen=True)
class Command:
    name: str
    arg: object = None


@dataclass(frozen=True)
class Button:
    rect: pygame.Rect
    command: Command


_KEYS: dict[int, Command] = {
    pygame.K_1: Command("element", ELEMENTS[0]),
    pygame.K_2: Command("element", ELEMENTS[1]),
    pygame.K_3: Command("element", ELEMENTS[2]),
    pygame.K_4: Command("element", ELEMENTS[3]),
    pygame.K_TAB: Command("next_element"),
    pygame.K_z: Command("demo", 0),
    pygame.K_x: Command("demo", 1),
    pygame.K_c: Command("demo", 2),
    pygame.K_v: Command("demo", 3),
    pygame.K_F1: Command("quality", "LOW"),
    pygame.K_F2: Command("quality", "MEDIUM"),
    pygame.K_F3: Command("quality", "HIGH"),
    pygame.K_a: Command("adaptive"),
    pygame.K_LEFTBRACKET: Command("sensitivity", -1),
    pygame.K_RIGHTBRACKET: Command("sensitivity", 1),
    pygame.K_MINUS: Command("effect_scale", -1),
    pygame.K_EQUALS: Command("effect_scale", 1),
    pygame.K_f: Command("fullscreen"),
    pygame.K_F11: Command("fullscreen"),
    pygame.K_b: Command("camera"),
    pygame.K_j: Command("landmarks"),
    pygame.K_h: Command("help"),
    pygame.K_BACKSPACE: Command("clear"),
    pygame.K_ESCAPE: Command("quit"),
}


def command_for_key(key: int) -> Command | None:
    return _KEYS.get(key)


def command_for_click(pos: tuple[int, int], buttons: Iterable[Button]) -> Command | None:
    for button in buttons:
        if button.rect.collidepoint(pos):
            return button.command
    return None


KEY_HELP: tuple[tuple[str, str], ...] = (
    ("1-4 / Tab", "element"),
    ("Z X C V", "test spell 1-4"),
    ("F1-F3", "quality"),
    ("A", "adaptive"),
    ("[ ]", "sensitivity"),
    ("- =", "effect size"),
    ("F", "fullscreen"),
    ("B", "webcam on/off"),
    ("J", "landmarks"),
    ("Bksp", "clear"),
    ("H", "help"),
    ("Esc", "quit"),
)
