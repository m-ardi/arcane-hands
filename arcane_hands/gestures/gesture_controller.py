"""Mengubah landmark tangan (piksel layar render) menjadi gestur tingkat tinggi.

Modul ini tidak bergantung pada MediaPipe, OpenCV, maupun Pygame sehingga bisa
diuji dengan landmark sintetis.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from arcane_hands.config import GestureConfig
from arcane_hands.utils.geometry import clamp, lerp, unit

PALM_IDS = (0, 5, 9, 13, 17)
FINGERS = ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))  # (mcp, pip, tip)
MAX_HANDS = 2


class Pose(Enum):
    OPEN = "Open palm"
    FIST = "Fist"
    PINCH = "Pinch"
    POINT = "Point"
    UNKNOWN = "Unknown"


def _zeros2() -> np.ndarray:
    return np.zeros(2, dtype=np.float32)


def _up() -> np.ndarray:
    return np.array((0.0, -1.0), dtype=np.float32)


@dataclass(slots=True)
class HandState:
    slot: int = 0
    points: np.ndarray = field(default_factory=lambda: np.zeros((21, 2), dtype=np.float32))
    palm: np.ndarray = field(default_factory=_zeros2)
    tip: np.ndarray = field(default_factory=_zeros2)
    pinch_point: np.ndarray = field(default_factory=_zeros2)
    aim: np.ndarray = field(default_factory=_up)
    size: float = 100.0
    pose: Pose = Pose.UNKNOWN
    pose_time: float = 0.0
    velocity: np.ndarray = field(default_factory=_zeros2)
    push: bool = False
    push_dir: np.ndarray = field(default_factory=_up)
    push_age: float = math.inf
    circling: int = 0
    circle_center: np.ndarray = field(default_factory=_zeros2)


@dataclass(slots=True)
class TwoHandState:
    distance: float = 0.0
    mid: np.ndarray = field(default_factory=_zeros2)
    together: bool = False
    together_time: float = 0.0
    near: bool = False
    apart_event: bool = False
    apart_age: float = math.inf
    raised: bool = False
    raised_time: float = 0.0


@dataclass(slots=True)
class GestureFrame:
    hands: tuple[HandState, ...] = ()
    two: TwoHandState | None = None

    def hand_by_slot(self, slot: int | None) -> HandState | None:
        for hand in self.hands:
            if hand.slot == slot:
                return hand
        return None

    @property
    def label(self) -> str:
        if not self.hands:
            return "No hands"
        parts = [f"H{h.slot + 1} {h.pose.value}" for h in self.hands]
        for hand in self.hands:
            if hand.push:
                parts.append("PUSH")
            if hand.circling:
                parts.append("CIRCLE")
        if self.two is not None:
            if self.two.together:
                parts.append("TOGETHER")
            if self.two.apart_event:
                parts.append("APART")
            if self.two.raised:
                parts.append("RAISED")
        return " | ".join(parts)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(math.hypot(a[0] - b[0], a[1] - b[1]))


def palm_center(points: np.ndarray) -> np.ndarray:
    return points[list(PALM_IDS)].mean(axis=0)


def classify_pose(points: np.ndarray, size: float, was_pinch: bool, cfg: GestureConfig) -> Pose:
    # Jari dianggap lurus bila ujungnya lebih jauh dari pergelangan daripada sendi PIP;
    # cara ini tidak bergantung pada rotasi tangan.
    wrist = points[0]
    extended = [
        _dist(points[tip], wrist) > _dist(points[pip], wrist) * cfg.extend_ratio
        for _, pip, tip in FINGERS
    ]
    pinch_ratio = _dist(points[4], points[8]) / size
    # Pada kepalan, ibu jari juga dekat dengan telunjuk; bedanya telunjuk saat mencubit masih menjulur.
    reach = _dist(points[8], wrist) / size
    min_reach = cfg.pinch_min_reach_hold if was_pinch else cfg.pinch_min_reach
    if pinch_ratio < (cfg.pinch_off if was_pinch else cfg.pinch_on) and reach >= min_reach:
        return Pose.PINCH
    count = sum(extended)
    if extended[0] and extended[1] and count >= 3:
        return Pose.OPEN
    if extended[0] and not extended[1] and not extended[2]:
        return Pose.POINT
    if count == 0:
        return Pose.FIST
    return Pose.UNKNOWN


@dataclass(slots=True)
class _Track:
    slot: int
    points: np.ndarray
    born: float
    seen: float
    palm: np.ndarray = field(default_factory=_zeros2)
    size: float = 100.0
    velocity: np.ndarray = field(default_factory=_zeros2)
    scale_rate: float = 0.0
    pose: Pose = Pose.UNKNOWN
    pose_candidate: Pose = Pose.UNKNOWN
    candidate_count: int = 0
    pose_since: float = 0.0
    aim: np.ndarray = field(default_factory=_up)
    push: bool = False
    push_dir: np.ndarray = field(default_factory=_up)
    push_armed: bool = True
    last_push: float = -math.inf
    history: deque = field(default_factory=lambda: deque(maxlen=64))
    circling: int = 0
    circle_center: np.ndarray = field(default_factory=_zeros2)


@dataclass(slots=True)
class _TwoMemory:
    together: bool = False
    together_since: float = 0.0
    together_last: float = -math.inf
    prev_dist: float | None = None
    prev_time: float = 0.0
    dist_rate: float = 0.0
    apart_event: bool = False
    last_apart: float = -math.inf
    raised_since: float | None = None


class GestureController:
    def __init__(self, cfg: GestureConfig, render_size: tuple[int, int], sensitivity: float = 1.0) -> None:
        self.cfg = cfg
        self.width, self.height = render_size
        self.sensitivity = sensitivity
        self._tracks: dict[int, _Track] = {}
        self._two = _TwoMemory()

    def reset(self) -> None:
        self._tracks.clear()
        self._two = _TwoMemory()

    def update(self, detections: list[np.ndarray], fresh: bool, now: float) -> GestureFrame:
        """detections hanya dipakai saat fresh=True; selain itu hasil terakhir dipertahankan."""
        for track in self._tracks.values():
            track.push = False
        self._two.apart_event = False
        if fresh:
            self._ingest(detections[:MAX_HANDS], now)
        for slot in [s for s, t in self._tracks.items() if now - t.seen > self.cfg.lost_grace]:
            del self._tracks[slot]
        if len(self._tracks) < 2:
            self._two = _TwoMemory()
        elif fresh:
            self._update_two(now)
        return self._build_frame(now)

    def _ingest(self, detections: list[np.ndarray], now: float) -> None:
        palms = [palm_center(d) for d in detections]
        pairs = sorted(
            (_dist(palms[i], track.palm), i, slot)
            for i in range(len(detections))
            for slot, track in self._tracks.items()
        )
        used_det: set[int] = set()
        used_slot: set[int] = set()
        for distance, i, slot in pairs:
            if i in used_det or slot in used_slot or distance > 0.35 * self.width:
                continue
            self._update_track(self._tracks[slot], detections[i], now)
            used_det.add(i)
            used_slot.add(slot)
        for i, points in enumerate(detections):
            if i in used_det:
                continue
            free = [s for s in range(MAX_HANDS) if s not in self._tracks]
            if free:
                self._tracks[free[0]] = self._new_track(free[0], points, now)

    def _new_track(self, slot: int, points: np.ndarray, now: float) -> _Track:
        pts = points.astype(np.float32).copy()
        track = _Track(slot=slot, points=pts, born=now, seen=now, pose_since=now)
        track.palm = palm_center(pts)
        track.size = max(_dist(pts[0], pts[9]), 1.0)
        self._refresh_pose(track, pts, now, immediate=True)
        return track

    def _update_track(self, track: _Track, detected: np.ndarray, now: float) -> None:
        cfg = self.cfg
        dt = max(now - track.seen, 1e-3)
        speed = _dist(palm_center(detected), track.palm) / dt
        alpha = lerp(cfg.smooth_min_alpha, cfg.smooth_max_alpha, clamp(speed / cfg.smooth_speed_ref, 0.0, 1.0))
        track.points += alpha * (detected - track.points)
        previous_palm, previous_size = track.palm, track.size
        track.palm = palm_center(track.points)
        track.size = max(_dist(track.points[0], track.points[9]), 1.0)
        track.velocity = 0.5 * track.velocity + 0.5 * (track.palm - previous_palm) / dt
        rate = (track.size - previous_size) / previous_size / dt
        track.scale_rate = 0.5 * track.scale_rate + 0.5 * rate
        track.seen = now
        self._refresh_pose(track, detected, now)
        self._detect_push(track, now)
        self._detect_circle(track, now)

    def _refresh_pose(self, track: _Track, raw_points: np.ndarray, now: float, immediate: bool = False) -> None:
        # Pose dibaca dari landmark mentah agar tidak tertinggal oleh smoothing; konfirmasi
        # beberapa update di bawah yang meredam noise.
        raw_size = max(_dist(raw_points[0], raw_points[9]), 1.0)
        raw = classify_pose(raw_points, raw_size, track.pose is Pose.PINCH, self.cfg)
        if immediate:
            track.pose = track.pose_candidate = raw
        elif raw is track.pose:
            track.candidate_count = 0
        else:
            if raw is track.pose_candidate:
                track.candidate_count += 1
            else:
                track.pose_candidate, track.candidate_count = raw, 1
            if track.candidate_count >= self.cfg.pose_confirm:
                track.pose = raw
                track.pose_since = now
                track.candidate_count = 0
        pts = track.points
        track.aim = unit(pts[8] - pts[5] if track.pose is Pose.POINT else pts[9] - pts[0])

    def _detect_push(self, track: _Track, now: float) -> None:
        cfg = self.cfg
        speed = math.hypot(track.velocity[0], track.velocity[1]) / self.width
        if not track.push_armed:
            quiet = speed < cfg.push_rearm_speed and track.scale_rate < 0.3
            if quiet and now - track.last_push >= cfg.push_cooldown:
                track.push_armed = True
            return
        if now - track.born < cfg.push_min_track_age:
            return
        by_speed = speed * self.sensitivity > cfg.push_speed
        by_scale = track.scale_rate * self.sensitivity > cfg.push_scale_rate
        if by_speed or by_scale:
            track.push = True
            track.push_armed = False
            track.last_push = now
            track.push_dir = unit(track.velocity) if by_speed else track.aim.copy()

    def _detect_circle(self, track: _Track, now: float) -> None:
        cfg = self.cfg
        history = track.history
        history.append((now, float(track.palm[0]), float(track.palm[1])))
        while history and now - history[0][0] > cfg.circle_window:
            history.popleft()
        if len(history) < 8:
            track.circling = 0
            return
        pts = np.array([(x, y) for _, x, y in history], dtype=np.float32)
        center = pts.mean(axis=0)
        rel = pts - center
        radii = np.hypot(rel[:, 0], rel[:, 1])
        mean_r = float(radii.mean())
        in_range = cfg.circle_min_radius * self.width <= mean_r <= cfg.circle_max_radius * self.width
        if not in_range or float(radii.std()) / mean_r > 0.5:
            track.circling = 0
            return
        angles = np.unwrap(np.arctan2(rel[:, 1], rel[:, 0]))
        total = float(angles[-1] - angles[0])
        needed = cfg.circle_min_angle * (0.6 if track.circling else 1.0)
        track.circling = 0 if abs(total) < needed else (1 if total > 0 else -1)
        track.circle_center = center

    def _update_two(self, now: float) -> None:
        cfg = self.cfg
        a, b = (self._tracks[s] for s in sorted(self._tracks))
        distance = _dist(a.palm, b.palm)
        average = (a.size + b.size) / 2
        ratio = distance / average
        mem = self._two
        if mem.prev_dist is not None:
            dt = max(now - mem.prev_time, 1e-3)
            mem.dist_rate = 0.5 * mem.dist_rate + 0.5 * (distance - mem.prev_dist) / dt
        mem.prev_dist, mem.prev_time = distance, now
        was_together = mem.together
        mem.together = ratio < (cfg.together_off if was_together else cfg.together_on)
        if mem.together and not was_together:
            mem.together_since = now
        if mem.together:
            mem.together_last = now
        opening = mem.dist_rate / average * self.sensitivity > cfg.apart_rate
        recently_together = now - mem.together_last < 0.6
        if opening and recently_together and now - mem.last_apart > cfg.apart_cooldown:
            mem.apart_event = True
            mem.last_apart = now
        high = max(a.palm[1], b.palm[1]) < cfg.raised_y * self.height
        both_open = a.pose is Pose.OPEN and b.pose is Pose.OPEN
        if high and both_open:
            if mem.raised_since is None:
                mem.raised_since = now
        else:
            mem.raised_since = None

    def _build_frame(self, now: float) -> GestureFrame:
        hands = tuple(self._hand_state(self._tracks[s], now) for s in sorted(self._tracks))
        two = None
        if len(hands) == 2:
            two = self._two_state(hands, now)
        return GestureFrame(hands=hands, two=two)

    def _hand_state(self, track: _Track, now: float) -> HandState:
        pts = track.points
        return HandState(
            slot=track.slot,
            points=pts,
            palm=track.palm.copy(),
            tip=pts[8].copy(),
            pinch_point=(pts[4] + pts[8]) / 2,
            aim=track.aim,
            size=track.size,
            pose=track.pose,
            pose_time=now - track.pose_since,
            velocity=track.velocity.copy(),
            push=track.push,
            push_dir=track.push_dir,
            push_age=now - track.last_push,
            circling=track.circling,
            circle_center=track.circle_center.copy(),
        )

    def _two_state(self, hands: tuple[HandState, ...], now: float) -> TwoHandState:
        mem = self._two
        a, b = hands
        distance = _dist(a.palm, b.palm)
        average = (a.size + b.size) / 2
        return TwoHandState(
            distance=distance,
            mid=(a.palm + b.palm) / 2,
            together=mem.together,
            together_time=now - mem.together_since if mem.together else 0.0,
            near=distance / average < self.cfg.near_ratio,
            apart_event=mem.apart_event,
            apart_age=now - mem.last_apart,
            raised=mem.raised_since is not None,
            raised_time=now - mem.raised_since if mem.raised_since is not None else 0.0,
        )
