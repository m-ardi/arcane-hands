"""Renderer 2D: latar webcam, lapisan efek aditif, flash/guncangan layar, dan penskalaan ke jendela."""

from __future__ import annotations

import math
import random
from typing import Callable

import numpy as np
import pygame

from arcane_hands.config import DisplayConfig, QualityPreset
from arcane_hands.graphics.palette import PALETTE_RGB, Color
from arcane_hands.graphics.particle_system import ParticleSystem
from arcane_hands.graphics.sprites import SpriteCache
from arcane_hands.utils.geometry import clamp

FLASH_DECAY = 4.0    # per detik
SHAKE_DECAY = 30.0   # piksel per detik
FLASH_GAIN = 0.55


def _rgb(color: int, intensity: float) -> tuple[int, int, int]:
    k = clamp(intensity, 0.0, 1.0)
    r, g, b = PALETTE_RGB[int(color)]
    return int(r * k), int(g * k), int(b * k)


def _int_points(points) -> list[list[int]]:
    return np.asarray(points).astype(np.int32).tolist()


class Renderer:
    def __init__(self, display: DisplayConfig, quality: QualityPreset) -> None:
        self.quality = quality
        self.render_size = display.render_size
        self.windowed_size = display.window_size
        self.fullscreen = False
        pygame.display.set_caption(display.caption)
        self.window = pygame.display.set_mode(self.windowed_size)
        self.scene = pygame.Surface(self.render_size).convert()
        self.fx = pygame.Surface(self.render_size).convert()
        self.background = pygame.Surface(self.render_size).convert()
        self.sprites = SpriteCache()
        self.sprites.warm()
        self._queue: list = []
        self._idle = self._make_idle_background()
        self._vignette = self._make_vignette()
        self._flash = 0.0
        self._flash_color = (255, 255, 255)
        self._shake = 0.0
        self.show_idle_background()
        self._update_layout()

    def set_quality(self, preset: QualityPreset) -> None:
        self.quality = preset

    def _make_idle_background(self) -> pygame.Surface:
        w, h = self.render_size
        x = (np.arange(w, dtype=np.float32) - w / 2) / (w / 2)
        y = (np.arange(h, dtype=np.float32) - h / 2) / (h / 2)
        r = np.clip(np.sqrt(x[:, None] ** 2 + y[None, :] ** 2) / 1.2, 0.0, 1.0)
        center = np.array((34, 20, 56), dtype=np.float32)
        edge = np.array((6, 4, 14), dtype=np.float32)
        arr = edge + (center - edge) * (1.0 - r)[..., None]
        return pygame.surfarray.make_surface(arr.astype(np.uint8)).convert()

    def _make_vignette(self) -> pygame.Surface:
        w, h = self.render_size
        x = (np.arange(w, dtype=np.float32) - w / 2) / (w / 2)
        y = (np.arange(h, dtype=np.float32) - h / 2) / (h / 2)
        r2 = np.clip((x[:, None] ** 2 + y[None, :] ** 2) / 2.0, 0.0, 1.0)
        value = (255 * (1.0 - 0.5 * r2)).astype(np.uint8)
        arr = np.repeat(value[..., None], 3, axis=2)
        return pygame.surfarray.make_surface(arr).convert()

    def _update_layout(self) -> None:
        ww, wh = self.window.get_size()
        rw, rh = self.render_size
        self._scale = min(ww / rw, wh / rh)
        self._fit = (round(rw * self._scale), round(rh * self._scale))
        self._offset = ((ww - self._fit[0]) // 2, (wh - self._fit[1]) // 2)
        self._scaled = pygame.Surface(self._fit).convert()
        self._exact_fit = self._fit == (ww, wh)
        self.window.fill((0, 0, 0))

    def set_fullscreen(self, enabled: bool) -> None:
        if enabled:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(self.windowed_size)
        self.fullscreen = enabled
        self._update_layout()

    def window_to_render(self, pos: tuple[int, int]) -> tuple[float, float]:
        return (pos[0] - self._offset[0]) / self._scale, (pos[1] - self._offset[1]) / self._scale

    def render_to_window(self, pos) -> tuple[int, int]:
        return round(pos[0] * self._scale + self._offset[0]), round(pos[1] * self._scale + self._offset[1])

    def update_background(self, rgb: np.ndarray) -> None:
        """rgb: array uint8 C-contiguous berukuran (tinggi, lebar, 3) sama dengan ukuran render."""
        w, h = self.render_size
        # frombuffer memakai memori array langsung, tanpa salinan.
        self.background.blit(pygame.image.frombuffer(rgb, (w, h), "RGB"), (0, 0))

    def show_idle_background(self) -> None:
        self.background.blit(self._idle, (0, 0))

    def add_flash(self, strength: float, color: tuple[int, int, int] = (255, 255, 255)) -> None:
        self._flash = max(self._flash, strength)
        self._flash_color = color

    def add_shake(self, amount: float) -> None:
        self._shake = max(self._shake, amount)

    def begin_frame(self, dt: float) -> None:
        self.scene.blit(self.background, (0, 0))
        self.fx.fill((0, 0, 0))
        self._flash = max(0.0, self._flash - dt * FLASH_DECAY)
        self._shake = max(0.0, self._shake - dt * SHAKE_DECAY)

    def glow(self, x: float, y: float, radius: float, color: int, intensity: float = 1.0) -> None:
        if intensity <= 0.02 or radius < 1.0:
            return
        entry = self.sprites.glow(color, radius, intensity)
        if entry is None:
            return
        surface, rect = entry
        self._queue.append((surface, (int(x - rect.w / 2), int(y - rect.h / 2)), rect, self.sprites.add_flag))

    def orb(self, x: float, y: float, radius: float, outer: int, inner: int, core: int,
            intensity: float = 1.0) -> None:
        """Bola energi dari beberapa lapisan glow; jumlah lapisan mengikuti preset kualitas."""
        layers = self.quality.glow_layers
        if layers <= 1:
            self.glow(x, y, radius * 2.4, inner, 0.9 * intensity)
        elif layers == 2:
            self.glow(x, y, radius * 3.0, outer, 0.5 * intensity)
            self.glow(x, y, radius * 1.5, core, intensity)
        else:
            self.glow(x, y, radius * 3.4, outer, 0.5 * intensity)
            self.glow(x, y, radius * 2.1, inner, 0.75 * intensity)
            self.glow(x, y, radius * 1.2, core, intensity)

    def ring(self, x: float, y: float, radius: float, color: int, intensity: float = 1.0, width: int = 2) -> None:
        r = int(radius)
        if r < 2 or intensity <= 0.02:
            return
        center = (int(x), int(y))
        pygame.draw.circle(self.fx, _rgb(color, intensity * 0.4), center, r, min(width + 4, r))
        pygame.draw.circle(self.fx, _rgb(color, intensity), center, r, min(width, r))

    def line(self, points, color: int, width: int = 1, intensity: float = 1.0) -> None:
        if intensity <= 0.02:
            return
        pts = _int_points(points)
        rgb = _rgb(color, intensity)
        if len(pts) == 2:
            pygame.draw.line(self.fx, rgb, pts[0], pts[1], width)
        elif len(pts) > 2:
            pygame.draw.lines(self.fx, rgb, False, pts, width)

    def polygon(self, points, color: int, intensity: float = 1.0) -> None:
        if intensity > 0.02:
            pygame.draw.polygon(self.fx, _rgb(color, intensity), _int_points(points))

    def shard(self, x: float, y: float, length: float, width: float, angle: float, color: int,
              intensity: float = 1.0) -> None:
        """Kristal es berbentuk belah ketupat memanjang, dengan glow lembut di bawahnya."""
        ux, uy = math.cos(angle), math.sin(angle)
        half_len, half_wid = length / 2, width / 2
        points = [
            (x + ux * half_len, y + uy * half_len),
            (x - uy * half_wid, y + ux * half_wid),
            (x - ux * half_len, y - uy * half_len),
            (x + uy * half_wid, y - ux * half_wid),
        ]
        self.glow(x, y, length * 0.9, color, 0.5 * intensity)
        self.polygon(points, color, intensity * 0.85)
        self.line([points[0], points[2]], Color.ICE_WHITE, 1, intensity)

    def draw_particles(self, particles: ParticleSystem) -> None:
        particles.draw(self.fx, self.sprites)

    def compose(self) -> None:
        """Menggabungkan lapisan efek ke scene, lalu menambah flash dan vignette bila aktif."""
        if self._queue:
            self.fx.blits(self._queue, False)
            self._queue.clear()
        self.scene.blit(self.fx, (0, 0), special_flags=pygame.BLEND_ADD)
        if self.quality.screen_fx and self._flash > 0.02:
            k = min(1.0, self._flash) * FLASH_GAIN
            color = tuple(int(c * k) for c in self._flash_color)
            self.scene.fill(color, special_flags=pygame.BLEND_ADD)
        if self.quality.vignette:
            self.scene.blit(self._vignette, (0, 0), special_flags=pygame.BLEND_MULT)

    def present(self, overlay: Callable[[pygame.Surface], None] | None = None) -> None:
        """Skala scene ke jendela; overlay (HUD) digambar pada resolusi jendela sebelum flip."""
        scale = pygame.transform.smoothscale if self.quality.smooth_scale else pygame.transform.scale
        shake = self._shake if self.quality.screen_fx else 0.0
        dx = random.randint(-int(shake), int(shake)) if shake >= 1.0 else 0
        dy = random.randint(-int(shake), int(shake)) if shake >= 1.0 else 0
        if self._exact_fit and dx == 0 and dy == 0:
            scale(self.scene, self._fit, self.window)
        else:
            scale(self.scene, self._fit, self._scaled)
            self.window.fill((0, 0, 0))
            self.window.blit(self._scaled, (self._offset[0] + dx, self._offset[1] + dy))
        if overlay is not None:
            overlay(self.window)
        pygame.display.flip()
