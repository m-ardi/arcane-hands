"""Landmark tangan sintetis (21 titik gaya MediaPipe) untuk menguji gestur tanpa webcam."""

from __future__ import annotations

import numpy as np

from arcane_hands.config import GestureConfig
from arcane_hands.gestures.gesture_controller import GestureController, GestureFrame

RENDER_SIZE = (960, 540)
FPS = 30
DT = 1.0 / FPS

_MCP_X = {5: -0.30, 9: 0.0, 13: 0.28, 17: 0.52}
_MCP_Y = {5: -0.95, 9: -1.0, 13: -0.95, 17: -0.85}
_EXTENDED = {
    "open": (1, 1, 1, 1),
    "fist": (0, 0, 0, 0),
    "point": (1, 0, 0, 0),
    "pinch": (1, 1, 1, 1),
}


def make_hand(pose: str, cx: float = 480.0, cy: float = 300.0, size: float = 90.0) -> np.ndarray:
    """Tangan menghadap ke atas; size = jarak pergelangan ke pangkal jari tengah."""
    pts = np.zeros((21, 2), dtype=np.float32)
    for mcp, extended in zip((5, 9, 13, 17), _EXTENDED[pose]):
        x, y = _MCP_X[mcp], _MCP_Y[mcp]
        pts[mcp] = (x, y)
        if extended:
            pts[mcp + 1], pts[mcp + 2], pts[mcp + 3] = (x, y - 0.45), (x, y - 0.7), (x, y - 0.95)
        else:
            pts[mcp + 1], pts[mcp + 2], pts[mcp + 3] = (x, y - 0.25), (x, y - 0.05), (x, y + 0.15)
    pts[1], pts[2] = (-0.35, -0.2), (-0.6, -0.4)
    if pose == "pinch":
        pts[6], pts[7], pts[8] = (-0.28, -1.25), (-0.2, -1.4), (-0.12, -1.5)
        pts[3], pts[4] = pts[8] + (-0.1, 0.1), pts[8] + (-0.05, 0.05)
    elif pose == "open":
        pts[3], pts[4] = (-0.8, -0.65), (-1.0, -0.85)
    else:
        pts[3], pts[4] = (-0.55, -0.55), (-0.5, -0.6)
    return pts * size + np.array((cx, cy), dtype=np.float32)


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def tick(self, dt: float = DT) -> float:
        self.now += dt
        return self.now


class Rig:
    """GestureController dengan jam buatan; setiap step() meniru satu frame kamera baru."""

    def __init__(self, sensitivity: float = 1.0) -> None:
        self.gestures = GestureController(GestureConfig(), RENDER_SIZE, sensitivity)
        self.clock = Clock()
        self.frame = GestureFrame()

    def step(self, *hands: np.ndarray) -> GestureFrame:
        self.frame = self.gestures.update(list(hands), True, self.clock.tick())
        return self.frame

    def hold(self, frames: int, *hands: np.ndarray) -> GestureFrame:
        for _ in range(frames):
            self.step(*hands)
        return self.frame
