"""Pengukuran FPS dan adaptive quality."""

from __future__ import annotations

from collections import deque

from arcane_hands.config import QUALITY_ORDER, AdaptiveConfig


class FrameMeter:
    """Rata-rata FPS dan waktu kerja per frame dalam jendela waktu pendek."""

    def __init__(self, window: float = 1.0) -> None:
        self.window = window
        self._frames: deque[tuple[float, float, float]] = deque()
        self.fps = 0.0
        self.work_ms = 0.0
        self.frame_ms = 0.0

    def add(self, now: float, frame_dt: float, work: float) -> None:
        """work = waktu kerja frame tanpa jeda menunggu clock."""
        self._frames.append((now, frame_dt, work))
        while self._frames and now - self._frames[0][0] > self.window:
            self._frames.popleft()
        n = len(self._frames)
        total = sum(f[1] for f in self._frames)
        self.fps = n / total if total > 0 else 0.0
        self.frame_ms = 1000.0 * total / n
        self.work_ms = 1000.0 * sum(f[2] for f in self._frames) / n


class DebugStats:
    """Ringkasan per detik untuk diagnosis: frame kamera baru, kecerahan, dan waktu deteksi tangan."""

    def __init__(self, now: float) -> None:
        self._since = now
        self._reset()

    def _reset(self) -> None:
        self.loops = 0
        self.camera_frames = 0
        self.dark_frames = 0
        self.brightness_sum = 0.0
        self.detects = 0
        self.detect_seconds = 0.0
        self.detect_max = 0.0

    def loop_frame(self) -> None:
        self.loops += 1

    def camera_frame(self, brightness: float) -> None:
        self.camera_frames += 1
        self.brightness_sum += brightness
        if brightness < 4.0:
            self.dark_frames += 1

    def detection(self, seconds: float) -> None:
        self.detects += 1
        self.detect_seconds += seconds
        self.detect_max = max(self.detect_max, seconds)

    def report(self, now: float, meter: FrameMeter, webcam_status: str, quality: str) -> str | None:
        if now - self._since < 1.0:
            return None
        cam = self.camera_frames
        text = (f"loop={self.loops}/s work={meter.work_ms:.1f}ms cam_frames={cam}/s dark={self.dark_frames} "
                f"brightness={self.brightness_sum / cam if cam else 0.0:.0f} "
                f"detect_avg={1000 * self.detect_seconds / self.detects if self.detects else 0.0:.1f}ms "
                f"detect_max={1000 * self.detect_max:.0f}ms webcam={webcam_status} quality={quality}")
        self._since = now
        self._reset()
        return text


class AdaptiveQuality:
    """Menurunkan preset bila FPS konsisten di bawah target, menaikkannya hanya saat stabil.

    Setelah penurunan, kenaikan ke level yang tadi gagal ditahan beberapa saat supaya
    kualitas tidak bolak-balik.
    """

    LEVEL_BLOCK_SECONDS = 60.0
    RISE_FPS_RATIO = 0.95

    def __init__(self, cfg: AdaptiveConfig, target_fps: int, start: str, now: float = 0.0) -> None:
        self.cfg = cfg
        self.target_fps = target_fps
        self.level = QUALITY_ORDER.index(start)
        self._bad_windows = 0
        self._stable_since: float | None = None
        self._last_eval = now
        self._last_change = now
        self._blocked_level: int | None = None
        self._blocked_until = 0.0

    def set_level(self, name: str, now: float) -> None:
        """Dipanggil saat pengguna memilih kualitas manual."""
        self.level = QUALITY_ORDER.index(name)
        self._bad_windows = 0
        self._stable_since = None
        self._last_change = now
        self._blocked_level = None

    def update(self, now: float, meter: FrameMeter) -> str | None:
        """Mengembalikan nama preset baru bila perlu berpindah, selain itu None."""
        if now - self._last_eval < self.cfg.eval_interval or not meter.fps:
            return None
        self._last_eval = now
        target = self.target_fps
        budget_ms = 1000.0 / target
        if meter.fps < target * self.cfg.drop_fps_ratio:
            self._bad_windows += 1
            self._stable_since = None
        else:
            self._bad_windows = 0
            idle = meter.work_ms < budget_ms * self.cfg.rise_busy_ratio
            if idle and meter.fps >= target * self.RISE_FPS_RATIO:
                if self._stable_since is None:
                    self._stable_since = now
            else:
                self._stable_since = None
        if now - self._last_change < self.cfg.min_change_gap:
            return None
        if self._bad_windows >= self.cfg.drop_windows and self.level > 0:
            self._blocked_level = self.level
            self._blocked_until = now + self.LEVEL_BLOCK_SECONDS
            return self._move(self.level - 1, now)
        stable = self._stable_since is not None and now - self._stable_since >= self.cfg.rise_stable_seconds
        if stable and self.level < len(QUALITY_ORDER) - 1:
            blocked = self._blocked_level == self.level + 1 and now < self._blocked_until
            if not blocked:
                return self._move(self.level + 1, now)
        return None

    def _move(self, level: int, now: float) -> str:
        self.level = level
        self._bad_windows = 0
        self._stable_since = None
        self._last_change = now
        return QUALITY_ORDER[level]
