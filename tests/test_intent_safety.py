import json
import tempfile
import unittest
from pathlib import Path

from robotlab.intent import HandIntent, IntentGate
from robotlab.safety import JointPoint, validate_trajectory
from robotlab.telemetry import TelemetryRecorder


class IntentTests(unittest.TestCase):
    def test_requires_stable_high_confidence_point(self):
        gate = IntentGate(stable_frames=3)
        results = [gate.update(HandIntent(0.5, 0.5, 0.9, timestamp_ms=i, track_id=2), now_ms=i)
                   for i in range(3)]
        self.assertEqual([result.status for result in results], ["confirming", "confirming", "accepted"])
        self.assertEqual(results[-1].cell, 4)

    def test_rejects_stale_or_wrong_gesture(self):
        gate = IntentGate(max_age_ms=100)
        self.assertEqual(gate.update(HandIntent(0.1, 0.1, 0.9, 0, gesture="open"), now_ms=0).reason,
                         "gesture_not_confirmed")
        self.assertEqual(gate.update(HandIntent(0.1, 0.1, 0.9, 0), now_ms=101).reason,
                         "stale_intent")


class SafetyTests(unittest.TestCase):
    def test_accepts_slow_six_joint_trajectory(self):
        points = (JointPoint(0.0, (0.0, -1.0, 1.0, -1.5, 0.0, 0.0)),
                  JointPoint(1.0, (0.2, -1.1, 1.1, -1.6, 0.1, 0.0)))
        report = validate_trajectory(points)
        self.assertTrue(report.accepted)
        self.assertEqual(report.point_count, 2)

    def test_rejects_speed_and_limit_violations(self):
        self.assertEqual(validate_trajectory((JointPoint(0, (0, -1, 1, -1, 0, 0)),
                                                JointPoint(0.1, (1, -1, 1, -1, 0, 0))),
                                             max_speed_rad_s=1).reason, "speed_limit")
        self.assertIn("joint_limit", validate_trajectory((JointPoint(0, (0, 1, 1, -1, 0, 0)),)).reason)


class TelemetryTests(unittest.TestCase):
    def test_writes_jsonl_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            recorder = TelemetryRecorder(path)
            recorder.record("intent_accepted", cell=4)
            recorder.record("safety_rejected", reason="stale")
            self.assertEqual(recorder.summary()["accepted_intents"], 1)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)
            json.loads(path.read_text(encoding="utf-8").splitlines()[0])
