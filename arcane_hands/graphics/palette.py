"""Palet warna global. Partikel menyimpan indeks warna agar sprite bisa di-cache per warna."""

from enum import IntEnum


class Color(IntEnum):
    FIRE_WHITE = 0
    FIRE_YELLOW = 1
    FIRE_ORANGE = 2
    FIRE_RED = 3
    EMBER = 4
    SMOKE = 5
    ICE_WHITE = 6
    ICE_LIGHT = 7
    ICE_CYAN = 8
    ICE_BLUE = 9
    BOLT_WHITE = 10
    BOLT_BLUE = 11
    ARC_WHITE = 12
    ARC_PINK = 13
    ARC_PURPLE = 14
    ARC_VIOLET = 15
    ARC_CYAN = 16
    ARC_BLUE = 17


PALETTE_RGB: tuple[tuple[int, int, int], ...] = (
    (255, 245, 205),
    (255, 212, 90),
    (255, 130, 34),
    (214, 46, 22),
    (255, 172, 64),
    (84, 72, 72),
    (235, 250, 255),
    (160, 220, 255),
    (60, 200, 240),
    (70, 120, 230),
    (240, 245, 255),
    (110, 150, 255),
    (245, 235, 255),
    (232, 124, 255),
    (170, 82, 255),
    (118, 62, 220),
    (82, 232, 255),
    (90, 120, 255),
)

PALETTE_SIZE = len(PALETTE_RGB)
assert PALETTE_SIZE == len(Color)
