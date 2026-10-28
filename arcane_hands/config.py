"""Konfigurasi aplikasi: kamera, tampilan, preset kualitas, gestur, dan adaptive quality.

Semua angka yang perlu disesuaikan ada di sini. Nilai awal untuk preset kualitas
hanyalah titik awal, bukan jaminan FPS pada perangkat tertentu.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QualityPreset:
    name: str
    max_particles: int
    max_effects: int
    density: float          # pengali jumlah emisi partikel
    glow_layers: int        # jumlah lapisan glow pada bola energi (1-3)
    trail_scale: float      # pengali kepadatan jejak proyektil
    bolt_levels: int        # tingkat subdivisi petir
    detect_every: int       # deteksi tangan setiap N frame kamera
    screen_fx: bool         # flash dan guncangan layar
    vignette: bool
    smooth_scale: bool      # smoothscale saat menskalakan ke jendela


QUALITY_PRESETS: dict[str, QualityPreset] = {
    "LOW": QualityPreset("LOW", 450, 2, 0.6, 1, 0.6, 3, 1, False, False, False),
    "MEDIUM": QualityPreset("MEDIUM", 900, 3, 1.0, 2, 1.0, 4, 1, True, True, True),
    "HIGH": QualityPreset("HIGH", 1400, 4, 1.4, 3, 1.4, 5, 1, True, True, True),
}
QUALITY_ORDER: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")

SENSITIVITY_RANGE = (0.5, 2.0)
EFFECT_SCALE_RANGE = (0.6, 1.6)


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    backend: str = "msmf" # "dshow", "msmf", atau "auto"
    mirror: bool = True


@dataclass(frozen=True)
class DisplayConfig:
    window_size: tuple[int, int] = (1280, 720)
    render_size: tuple[int, int] = (960, 540)
    target_fps: int = 30
    caption: str = "Arcane Hands"


@dataclass(frozen=True)
class TrackingConfig:
    max_hands: int = 2
    model_complexity: int = 0
    detection_confidence: float = 0.6
    tracking_confidence: float = 0.5


@dataclass(frozen=True)
class GestureConfig:
    smooth_min_alpha: float = 0.25
    smooth_max_alpha: float = 0.85
    smooth_speed_ref: float = 1200.0   # px/detik; di atas ini smoothing paling ringan
    lost_grace: float = 0.25           # detik tangan dipertahankan setelah hilang
    pose_confirm: int = 2              # jumlah update berturut-turut untuk mengganti pose
    extend_ratio: float = 1.08
    pinch_on: float = 0.30
    pinch_off: float = 0.40
    pinch_min_reach: float = 1.15      # jarak ujung telunjuk ke pergelangan / ukuran telapak
    pinch_min_reach_hold: float = 1.0  # batas lebih longgar saat pinch sudah aktif
    push_speed: float = 0.75           # lebar layar per detik
    push_scale_rate: float = 1.0       # perubahan ukuran telapak per detik
    push_rearm_speed: float = 0.35
    push_cooldown: float = 0.45
    push_min_track_age: float = 0.2
    circle_window: float = 1.1
    circle_min_angle: float = 4.2      # radian (sekitar 240 derajat)
    circle_min_radius: float = 0.03    # relatif terhadap lebar layar
    circle_max_radius: float = 0.30
    together_on: float = 2.6           # jarak telapak / ukuran tangan rata-rata
    together_off: float = 3.2
    near_ratio: float = 4.5
    apart_rate: float = 3.5            # ukuran tangan per detik
    apart_cooldown: float = 0.8
    raised_y: float = 0.42             # batas atas layar (fraksi tinggi)


@dataclass(frozen=True)
class AdaptiveConfig:
    eval_interval: float = 1.0
    drop_fps_ratio: float = 0.85
    drop_windows: int = 3
    rise_busy_ratio: float = 0.6
    rise_stable_seconds: float = 12.0
    min_change_gap: float = 8.0


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    gestures: GestureConfig = field(default_factory=GestureConfig)
    adaptive: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    quality: str = "LOW"
    adaptive_enabled: bool = True
    sensitivity: float = 1.0
    effect_scale: float = 1.0
    start_camera: bool = True
    start_fullscreen: bool = False
    debug: bool = False


def validate_config(cfg: AppConfig) -> AppConfig:
    """Memeriksa nilai konfigurasi dan melempar ValueError bila tidak masuk akal."""
    if cfg.quality not in QUALITY_PRESETS:
        raise ValueError(f"Preset kualitas tidak dikenal: {cfg.quality!r}")
    if cfg.camera.backend not in ("dshow", "msmf", "auto"):
        raise ValueError(f"Backend kamera tidak dikenal: {cfg.camera.backend!r}")
    if min(cfg.camera.width, cfg.camera.height, cfg.camera.fps) <= 0:
        raise ValueError("Resolusi dan FPS kamera harus positif")
    if min(*cfg.display.window_size, *cfg.display.render_size) <= 0:
        raise ValueError("Ukuran jendela dan render harus positif")
    if cfg.display.target_fps <= 0:
        raise ValueError("target_fps harus positif")
    if not SENSITIVITY_RANGE[0] <= cfg.sensitivity <= SENSITIVITY_RANGE[1]:
        raise ValueError(f"sensitivity harus dalam {SENSITIVITY_RANGE}")
    if not EFFECT_SCALE_RANGE[0] <= cfg.effect_scale <= EFFECT_SCALE_RANGE[1]:
        raise ValueError(f"effect_scale harus dalam {EFFECT_SCALE_RANGE}")
    if not 1 <= cfg.tracking.max_hands <= 2:
        raise ValueError("max_hands harus 1 atau 2")
    if cfg.tracking.model_complexity not in (0, 1):
        raise ValueError("model_complexity harus 0 atau 1")
    for preset in QUALITY_PRESETS.values():
        if min(preset.max_particles, preset.max_effects, preset.detect_every) < 1:
            raise ValueError(f"Preset {preset.name} berisi batas yang tidak valid")
        if not 1 <= preset.glow_layers <= 3:
            raise ValueError(f"glow_layers preset {preset.name} harus 1-3")
    return cfg
