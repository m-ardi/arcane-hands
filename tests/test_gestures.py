import math
import unittest

import numpy as np

from arcane_hands.config import GestureConfig
from arcane_hands.gestures.gesture_controller import Pose, classify_pose
from tests.synthetic import DT, Rig, make_hand


def _size(points: np.ndarray) -> float:
    return float(np.hypot(*(points[0] - points[9])))


class PoseTests(unittest.TestCase):
    def test_each_pose_is_recognised(self):
        cfg = GestureConfig()
        expected = {"open": Pose.OPEN, "fist": Pose.FIST, "point": Pose.POINT, "pinch": Pose.PINCH}
        for name, pose in expected.items():
            hand = make_hand(name)
            self.assertIs(classify_pose(hand, _size(hand), False, cfg), pose, name)

    def test_pose_is_independent_of_scale_and_rotation(self):
        cfg = GestureConfig()
        hand = make_hand("point", size=40.0)
        angle = 1.1
        rot = np.array(((math.cos(angle), -math.sin(angle)), (math.sin(angle), math.cos(angle))), dtype=np.float32)
        hand = (hand - hand[0]) @ rot.T + hand[0]
        self.assertIs(classify_pose(hand, _size(hand), False, cfg), Pose.POINT)

    def test_fist_is_not_mistaken_for_pinch(self):
        # Ibu jari pada kepalan dekat dengan telunjuk, tetapi telunjuknya melengkung.
        hand = make_hand("fist")
        hand[4] = hand[8] + np.array((-3.0, 4.0), dtype=np.float32)
        self.assertIs(classify_pose(hand, _size(hand), False, GestureConfig()), Pose.FIST)

    def test_pose_change_needs_confirmation(self):
        rig = Rig()
        rig.hold(5, make_hand("open"))
        self.assertIs(rig.frame.hands[0].pose, Pose.OPEN)
        rig.step(make_hand("fist"))
        self.assertIs(rig.frame.hands[0].pose, Pose.OPEN)
        rig.step(make_hand("fist"))
        self.assertIs(rig.frame.hands[0].pose, Pose.FIST)

    def test_single_noisy_frame_does_not_flip_pose(self):
        rig = Rig()
        rig.hold(5, make_hand("open"))
        rig.step(make_hand("fist"))
        rig.step(make_hand("open"))
        self.assertIs(rig.frame.hands[0].pose, Pose.OPEN)


class MotionTests(unittest.TestCase):
    def test_fast_move_triggers_one_push(self):
        rig = Rig()
        rig.hold(10, make_hand("fist", 300, 300))
        pushes = 0
        for i in range(1, 16):
            frame = rig.step(make_hand("fist", 300 + 38 * i, 300))
            pushes += sum(h.push for h in frame.hands)
        self.assertEqual(pushes, 1)

    def test_push_direction_follows_motion(self):
        rig = Rig()
        rig.hold(10, make_hand("fist", 480, 150))
        direction = None
        for i in range(1, 12):
            frame = rig.step(make_hand("fist", 480, 150 + 38 * i))
            if frame.hands[0].push:
                direction = frame.hands[0].push_dir
        self.assertIsNotNone(direction)
        self.assertGreater(direction[1], 0.9)

    def test_slow_move_does_not_push(self):
        rig = Rig()
        rig.hold(10, make_hand("fist", 300, 300))
        for i in range(1, 60):
            frame = rig.step(make_hand("fist", 300 + 3 * i, 300))
            self.assertFalse(frame.hands[0].push)

    def test_new_hand_cannot_push_immediately(self):
        rig = Rig()
        for i in range(5):
            frame = rig.step(make_hand("fist", 100 + 60 * i, 300))
            self.assertFalse(any(h.push for h in frame.hands))

    def test_circular_motion_is_detected(self):
        rig = Rig()
        direction = 0
        for i in range(60):
            angle = i * DT * 5.5
            frame = rig.step(make_hand("point", 480 + 70 * math.cos(angle), 300 + 70 * math.sin(angle)))
            direction = frame.hands[0].circling or direction
        self.assertNotEqual(direction, 0)

    def test_straight_motion_is_not_a_circle(self):
        rig = Rig()
        for i in range(60):
            frame = rig.step(make_hand("point", 200 + 8 * i, 300))
            self.assertEqual(frame.hands[0].circling, 0)

    def test_still_hand_is_not_a_circle(self):
        rig = Rig()
        frame = rig.hold(60, make_hand("point"))
        self.assertEqual(frame.hands[0].circling, 0)


class TwoHandTests(unittest.TestCase):
    def test_hands_close_together_are_flagged(self):
        rig = Rig()
        frame = rig.hold(8, make_hand("open", 420, 300), make_hand("open", 560, 300))
        self.assertTrue(frame.two.together)
        self.assertTrue(frame.two.near)

    def test_distant_hands_are_not_together(self):
        rig = Rig()
        frame = rig.hold(8, make_hand("open", 200, 300), make_hand("open", 760, 300))
        self.assertFalse(frame.two.together)

    def test_pulling_apart_fires_once(self):
        rig = Rig()
        rig.hold(10, make_hand("open", 420, 300), make_hand("open", 560, 300))
        events = 0
        for i in range(1, 16):
            frame = rig.step(make_hand("open", 420 - 18 * i, 300), make_hand("open", 560 + 18 * i, 300))
            events += frame.two.apart_event
        self.assertEqual(events, 1)

    def test_apart_without_being_together_does_not_fire(self):
        rig = Rig()
        rig.hold(10, make_hand("open", 250, 300), make_hand("open", 700, 300))
        for i in range(1, 12):
            frame = rig.step(make_hand("open", 250 - 10 * i, 300), make_hand("open", 700 + 10 * i, 300))
            self.assertFalse(frame.two.apart_event)

    def test_raised_open_hands(self):
        rig = Rig()
        frame = rig.hold(10, make_hand("open", 300, 170), make_hand("open", 660, 170))
        self.assertTrue(frame.two.raised)

    def test_lowered_hands_are_not_raised(self):
        rig = Rig()
        frame = rig.hold(10, make_hand("open", 300, 400), make_hand("open", 660, 400))
        self.assertFalse(frame.two.raised)


class TrackingLossTests(unittest.TestCase):
    def test_hand_survives_brief_dropout(self):
        rig = Rig()
        rig.hold(6, make_hand("open"))
        frame = rig.gestures.update([], True, rig.clock.tick())
        self.assertEqual(len(frame.hands), 1)

    def test_hand_disappears_after_grace(self):
        rig = Rig()
        rig.hold(6, make_hand("open"))
        for _ in range(12):
            frame = rig.gestures.update([], True, rig.clock.tick())
        self.assertEqual(frame.hands, ())

    def test_no_push_event_while_hand_is_missing(self):
        rig = Rig()
        rig.hold(10, make_hand("fist", 300, 300))
        for _ in range(20):
            frame = rig.gestures.update([], True, rig.clock.tick())
            self.assertFalse(any(h.push for h in frame.hands))

    def test_hands_keep_their_slots(self):
        rig = Rig()
        rig.hold(6, make_hand("open", 250, 300), make_hand("open", 700, 300))
        slots = {tuple(h.palm.round()): h.slot for h in rig.frame.hands}
        rig.hold(6, make_hand("open", 700, 300), make_hand("open", 250, 300))
        for hand in rig.frame.hands:
            self.assertEqual(slots[tuple(hand.palm.round())], hand.slot)


if __name__ == "__main__":
    unittest.main()
