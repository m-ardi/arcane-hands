"""Akses webcam dengan satu thread pembaca yang hanya menyimpan frame terbaru."""

from __future__ import annotations

import logging
import threading
import time

import cv2
import numpy as np

from arcane_hands.config import CameraConfig

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 90


class CameraError(RuntimeError):
    pass


def _backend_flag(name: str) -> int:
    return {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}.get(name, cv2.CAP_ANY)


class WebcamReader:
    def __init__(self, cfg: CameraConfig) -> None:
        self._cfg = cfg
        self._cap: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._seq = 0
        self.error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        cap = cv2.VideoCapture(self._cfg.index, _backend_flag(self._cfg.backend))
        if not cap.isOpened():
            cap.release()
            raise CameraError(f"Webcam {self._cfg.index} tidak bisa dibuka")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self._cfg.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        self._stop.clear()
        self.error = None
        self._frame = None
        self._thread = threading.Thread(target=self._run, name="webcam-reader", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        failures = 0
        cap = self._cap
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    self.error = "Webcam berhenti mengirim frame"
                    return
                time.sleep(0.01)
                continue
            failures = 0
            with self._lock:
                self._frame = frame
                self._seq += 1

    def read_new(self, last_seq: int) -> tuple[np.ndarray | None, int]:
        """Mengembalikan frame terbaru jika lebih baru dari last_seq."""
        with self._lock:
            if self._frame is None or self._seq == last_seq:
                return None, last_seq
            return self._frame, self._seq

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._frame = None
            self._seq = 0


def prepare_frame(frame_bgr: np.ndarray, aspect: float, mirror: bool, max_width: int = 640) -> np.ndarray:
    """Crop tengah ke rasio layar render, kecilkan, mirror, lalu konversi ke RGB."""
    h, w = frame_bgr.shape[:2]
    target_h = round(w / aspect)
    if target_h <= h:
        top = (h - target_h) // 2
        crop = frame_bgr[top:top + target_h]
    else:
        target_w = round(h * aspect)
        left = (w - target_w) // 2
        crop = frame_bgr[:, left:left + target_w]
    if crop.shape[1] > max_width:
        # Kecilkan sebelum flip dan konversi warna; memproses frame 720p penuh jauh lebih mahal.
        crop = cv2.resize(crop, (max_width, round(max_width / aspect)), interpolation=cv2.INTER_AREA)
    if mirror:
        crop = cv2.flip(crop, 1)
    return cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
