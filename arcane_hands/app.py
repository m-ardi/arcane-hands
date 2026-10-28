"""Siklus hidup aplikasi: menghubungkan kamera, gestur, spell, renderer, dan HUD."""

from __future__ import annotations

import logging
import time
from dataclasses import replace

import cv2
import numpy as np
import pygame

from arcane_hands.camera.hand_tracker import HandTracker, TrackingUnavailable
from arcane_hands.camera.webcam import CameraError, WebcamReader, prepare_frame
from arcane_hands.config import (
    EFFECT_SCALE_RANGE,
    QUALITY_ORDER,
    QUALITY_PRESETS,
    SENSITIVITY_RANGE,
    AppConfig,
    validate_config,
)
from arcane_hands.gestures.gesture_controller import GestureController, GestureFrame
from arcane_hands.graphics.effects.base import EffectContext
from arcane_hands.graphics.particle_system import ParticleSystem
from arcane_hands.graphics.renderer import Renderer
from arcane_hands.interface.controls import Command, command_for_click, command_for_key
from arcane_hands.interface.hud import Hud, HudView
from arcane_hands.spells.catalog import ELEMENTS, spells_for, validate_catalog
from arcane_hands.spells.spell_manager import SpellManager
from arcane_hands.utils.performance import AdaptiveQuality, DebugStats, FrameMeter

log = logging.getLogger(__name__)

MAX_DT = 0.05            # batas dt supaya jeda besar tidak membuat partikel melompat
STEP = 0.1               # langkah sensitivitas dan ukuran efek
CAMERA_DIM = 0.8         # redupkan feed webcam agar efek aditif tetap terlihat
DEMO_ANCHOR = (0.4, 0.62)
DARK_FRAME_LEVEL = 4.0   # rata-rata piksel (0-255) di bawah ini dianggap frame kosong
DARK_FRAMES_WARN = 30    # berapa frame gelap berturut-turut sebelum HUD memberi peringatan


class App:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = validate_config(cfg)
        validate_catalog()
        self.running = False
        self.quality_name = cfg.quality
        self.adaptive_on = cfg.adaptive_enabled
        self.sensitivity = cfg.sensitivity
        self.effect_scale = cfg.effect_scale
        self.show_help = True
        self.show_landmarks = False
        self.camera_on = cfg.start_camera
        self.webcam_status = "off"
        self.tracking_status = "off"
        self._detections: list[np.ndarray] = []
        self._frame_seq = 0
        self._camera_frames = 0
        self._gesture_frame = GestureFrame()
        self.webcam: WebcamReader | None = None
        self.tracker: HandTracker | None = None

        pygame.init()
        preset = QUALITY_PRESETS[self.quality_name]
        display = cfg.display
        self.renderer = Renderer(display, preset)
        self.particles = ParticleSystem(max(p.max_particles for p in QUALITY_PRESETS.values()))
        ctx = EffectContext(self.particles, display.render_size, preset,
                            on_flash=self.renderer.add_flash, on_shake=self.renderer.add_shake)
        self.spells = SpellManager(ctx, "Fire", self.effect_scale, self.sensitivity)
        self.gestures = GestureController(cfg.gestures, display.render_size, self.sensitivity)
        self.hud = Hud(self.renderer.window.get_size(), self.renderer.render_to_window)
        self.meter = FrameMeter()
        self.adaptive = AdaptiveQuality(cfg.adaptive, display.target_fps, self.quality_name, time.perf_counter())
        self.clock = pygame.time.Clock()
        self._dark_frames = 0
        self._stats = DebugStats(time.perf_counter()) if cfg.debug else None
        self._apply_quality(self.quality_name)
        if cfg.start_fullscreen:
            self._toggle_fullscreen()

    def run(self) -> None:
        self.running = True
        self._start_tracker()
        if self.camera_on:
            self._start_camera()
        try:
            self._loop()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.running = False
        self._stop_camera()
        if self.tracker is not None:
            self.tracker.close()
            self.tracker = None
        pygame.quit()

    def _loop(self) -> None:
        previous_start = time.perf_counter()
        while self.running:
            now = time.perf_counter()
            # dt diukur antar awal frame; menghitung dari akhir frame akan selalu mendekati nol.
            dt = min(now - previous_start, MAX_DT)
            previous_start = now
            self._handle_events()
            self._update(dt, now)
            self._draw(dt)
            work = time.perf_counter() - now
            self.clock.tick(self.cfg.display.target_fps)
            end = time.perf_counter()
            self.meter.add(end, end - now, work)
            self._adapt(end)
            if self._stats is not None:
                self._stats.loop_frame()
                report = self._stats.report(end, self.meter, self.webcam_status, self.quality_name)
                if report:
                    log.info(report)

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            command = None
            if event.type == pygame.QUIT:
                command = Command("quit")
            elif event.type == pygame.KEYDOWN:
                command = command_for_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                command = command_for_click(event.pos, self.hud.buttons)
            if command is not None:
                self._execute(command)

    def _execute(self, command: Command) -> None:
        name, arg = command.name, command.arg
        if name == "quit":
            self.running = False
        elif name == "element":
            self._select_element(str(arg))
        elif name == "next_element":
            self.spells.cycle_element()
            self.hud.notify(f"Element: {self.spells.element}")
        elif name == "demo":
            self._demo(int(arg))
        elif name == "quality":
            self._set_quality_manual(str(arg))
        elif name == "adaptive":
            self.adaptive_on = not self.adaptive_on
            self.hud.notify(f"Adaptive quality {'ON' if self.adaptive_on else 'OFF'}")
        elif name == "sensitivity":
            self._set_sensitivity(self.sensitivity + STEP * int(arg))
        elif name == "effect_scale":
            self._set_effect_scale(self.effect_scale + STEP * int(arg))
        elif name == "fullscreen":
            self._toggle_fullscreen()
        elif name == "camera":
            self._toggle_camera()
        elif name == "landmarks":
            self.show_landmarks = not self.show_landmarks
        elif name == "help":
            self.show_help = not self.show_help
        elif name == "clear":
            self.spells.clear()
            self.particles.clear()

    def _select_element(self, element: str) -> None:
        self.spells.select_element(element)
        self.hud.notify(f"Element: {element}")

    def _demo(self, index: int) -> None:
        choices = spells_for(self.spells.element)
        if not 0 <= index < len(choices):
            return
        w, h = self.cfg.display.render_size
        anchor = (w * DEMO_ANCHOR[0], h * DEMO_ANCHOR[1])
        if self.spells.demo_cast(choices[index].key, anchor):
            self.hud.notify(f"Test: {choices[index].name}")

    def _set_sensitivity(self, value: float) -> None:
        self.sensitivity = round(min(max(value, SENSITIVITY_RANGE[0]), SENSITIVITY_RANGE[1]), 2)
        self.gestures.sensitivity = self.sensitivity
        self.spells.sensitivity = self.sensitivity

    def _set_effect_scale(self, value: float) -> None:
        self.effect_scale = round(min(max(value, EFFECT_SCALE_RANGE[0]), EFFECT_SCALE_RANGE[1]), 2)
        self.spells.effect_scale = self.effect_scale

    def _apply_quality(self, name: str) -> None:
        preset = QUALITY_PRESETS[name]
        self.quality_name = name
        self.renderer.set_quality(preset)
        self.particles.apply_quality(preset)
        self.spells.set_quality(preset)

    def _set_quality_manual(self, name: str) -> None:
        self._apply_quality(name)
        self.adaptive.set_level(name, time.perf_counter())
        self.hud.notify(f"Quality: {name}")

    def _adapt(self, now: float) -> None:
        if not self.adaptive_on:
            return
        new = self.adaptive.update(now, self.meter)
        if new is not None and new != self.quality_name:
            self._apply_quality(new)
            self.hud.notify(f"Adaptive quality: {new}")

    def _toggle_fullscreen(self) -> None:
        self.renderer.set_fullscreen(not self.renderer.fullscreen)
        self.hud.resize(self.renderer.window.get_size())

    def _start_tracker(self) -> None:
        try:
            self.tracker = HandTracker(self.cfg.tracking, self.cfg.display.render_size)
            self.tracking_status = "waiting"
        except TrackingUnavailable as exc:
            log.warning("Hand tracking tidak tersedia: %s", exc)
            self.tracking_status = "unavailable"

    def _start_camera(self) -> None:
        self.webcam = WebcamReader(self.cfg.camera)
        try:
            self.webcam.start()
            self.webcam_status = "ok"
        except CameraError as exc:
            log.warning("%s", exc)
            self.webcam = None
            self.webcam_status = "unavailable"
            self.camera_on = False

    def _stop_camera(self) -> None:
        if self.webcam is not None:
            self.webcam.stop()
            self.webcam = None
        self._frame_seq = 0
        self._detections = []

    def _toggle_camera(self) -> None:
        if self.camera_on:
            self.camera_on = False
            self._stop_camera()
            self.webcam_status = "off"
            if self.tracker is not None:
                self.tracking_status = "waiting"
            self.gestures.reset()
            self.renderer.show_idle_background()
        else:
            self.camera_on = True
            self._start_camera()
        self.hud.notify(f"Webcam {'on' if self.camera_on else 'off'}")

    def _update(self, dt: float, now: float) -> None:
        fresh = self._poll_camera()
        self._gesture_frame = self.gestures.update(self._detections, fresh, now)
        self.spells.update(self._gesture_frame, dt)
        self.particles.update(dt)
        self.hud.tick(dt)

    def _poll_camera(self) -> bool:
        """Mengembalikan True bila deteksi tangan baru saja dijalankan pada frame kamera baru."""
        webcam = self.webcam
        if webcam is None:
            return False
        if webcam.error:
            self.webcam_status = "error"
            return False
        frame, self._frame_seq = webcam.read_new(self._frame_seq)
        if frame is None:
            return False
        brightness = sum(cv2.mean(frame)[:3]) / 3
        if self._stats is not None:
            self._stats.camera_frame(brightness)
        if brightness < DARK_FRAME_LEVEL:
            # Frame hitam sesekali (kamera IR, exposure, penutup webcam) dibuang; background tetap frame terakhir.
            self._dark_frames += 1
            if self._dark_frames >= DARK_FRAMES_WARN:
                self.webcam_status = "dark frames (shutter / IR camera?)"
            return False
        self._dark_frames = 0
        self.webcam_status = "ok"
        self._camera_frames += 1
        rgb = prepare_frame(frame, self._aspect(), self.cfg.camera.mirror)
        self._show_camera(rgb)
        every = QUALITY_PRESETS[self.quality_name].detect_every
        if self.tracker is None or self._camera_frames % every:
            return False
        started = time.perf_counter()
        self._detections = self.tracker.process(rgb)
        if self._stats is not None:
            self._stats.detection(time.perf_counter() - started)
        self.tracking_status = "ok" if self._detections else "no hand"
        return True

    def _aspect(self) -> float:
        w, h = self.cfg.display.render_size
        return w / h

    def _show_camera(self, rgb: np.ndarray) -> None:
        w, h = self.cfg.display.render_size
        dimmed = cv2.convertScaleAbs(rgb, alpha=CAMERA_DIM)
        # Memakai nilai kembalian, bukan buffer dst, agar hasilnya pasti array baru yang contiguous.
        self.renderer.update_background(np.ascontiguousarray(cv2.resize(dimmed, (w, h))))

    def _draw(self, dt: float) -> None:
        r = self.renderer
        r.begin_frame(dt)
        for effect in self.spells.effects:
            effect.draw(r)
        r.draw_particles(self.particles)
        r.compose()
        r.present(lambda window: self.hud.draw(window, self._view()))

    def _view(self) -> HudView:
        points = [tuple(p) for hand in self._gesture_frame.hands for p in hand.points] if self.show_landmarks else []
        return HudView(
            fps=self.meter.fps,
            frame_ms=self.meter.frame_ms,
            particles=self.particles.count,
            particle_limit=self.particles.limit,
            quality=self.quality_name,
            adaptive=self.adaptive_on,
            sensitivity=self.sensitivity,
            effect_scale=self.effect_scale,
            element=self.spells.element,
            status=self.spells.status(),
            gesture_label=self._gesture_frame.label,
            webcam_status=self.webcam_status,
            tracking_status=self.tracking_status,
            fullscreen=self.renderer.fullscreen,
            camera_on=self.camera_on,
            show_help=self.show_help,
            show_landmarks=self.show_landmarks,
            hand_points=points,
        )


def build_config(quality: str | None, camera_index: int | None, no_camera: bool, fullscreen: bool,
                debug: bool = False) -> AppConfig:
    cfg = AppConfig(start_camera=not no_camera, start_fullscreen=fullscreen, debug=debug)
    if quality is not None:
        cfg = replace(cfg, quality=quality)
    if camera_index is not None:
        cfg = replace(cfg, camera=replace(cfg.camera, index=camera_index))
    return cfg


def run(cfg: AppConfig) -> None:
    level = logging.INFO if cfg.debug else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    App(cfg).run()
