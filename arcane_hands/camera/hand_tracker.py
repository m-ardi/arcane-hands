"""Pembungkus MediaPipe Hands yang menghasilkan landmark dalam piksel layar render."""

from __future__ import annotations

import numpy as np

from arcane_hands.config import TrackingConfig


class TrackingUnavailable(RuntimeError):
    pass


class HandTracker:
    def __init__(self, cfg: TrackingConfig, render_size: tuple[int, int]) -> None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise TrackingUnavailable("MediaPipe belum terpasang") from exc
        # API solutions sudah dihapus di MediaPipe versi baru; versi di requirements.txt masih punya.
        if not hasattr(mp, "solutions"):
            raise TrackingUnavailable(
                "Versi MediaPipe ini tidak punya API solutions. Pasang versi dari requirements.txt."
            )
        self._scale = np.array(render_size, dtype=np.float32)
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=cfg.max_hands,
            model_complexity=cfg.model_complexity,
            min_detection_confidence=cfg.detection_confidence,
            min_tracking_confidence=cfg.tracking_confidence,
        )

    def process(self, rgb: np.ndarray) -> list[np.ndarray]:
        """Frame RGB hasil crop; hasilnya daftar array (21, 2) dalam piksel render."""
        rgb.flags.writeable = False
        result = self._hands.process(rgb)
        rgb.flags.writeable = True
        if not result.multi_hand_landmarks:
            return []
        return [
            np.array([(lm.x, lm.y) for lm in hand.landmark], dtype=np.float32) * self._scale
            for hand in result.multi_hand_landmarks
        ]

    def close(self) -> None:
        self._hands.close()
