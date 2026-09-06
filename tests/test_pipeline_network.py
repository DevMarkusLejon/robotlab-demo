import tempfile
import unittest
from pathlib import Path

from robotlab.intent import HandIntent, IntentGate
from robotlab.network import NetworkSimulator
from robotlab.pipeline import SharedAutonomyPipeline
from robotlab.safety import JointPoint
from robotlab.telemetry import TelemetryRecorder
from robotlab.metrics import percentile, summarize_events


class NetworkTests(unittest.TestCase):
    def test_percentile_and_event_metrics_are_deterministic(self):
        self.assertEqual(percentile([100, 20, 40], 0.5), 40)
        summary = summarize_events([
            {"event": "trajectory_checked", "accepted": True},
            {"event": "placement_verified"},
            {"event": "transport_delivered", "latency_ms": 40},
            {"event": "transport_delivered", "latency_ms": 80},
        ])
        self.assertEqual(summary["trajectory_acceptance_rate"], 1.0)
        self.assertEqual(summary["transport_latency_p95_ms"], 80.0)

    def test_delivers_within_deadline_and_rejects_expiry(self):
        network = NetworkSimulator(latency_ms=50)
        self.assertTrue(network.deliver({}, sent_at_ms=0, deadline_ms=50).delivered)
        self.assertEqual(network.deliver({}, sent_at_ms=0, deadline_ms=49).reason, "deadline_expired")

    def test_deterministic_packet_loss(self):
        result = NetworkSimulator(drop_rate=1.0).deliver({}, sent_at_ms=10, deadline_ms=100)
        self.assertFalse(result.delivered)
        self.assertEqual(result.reason, "packet_loss")


class PipelineTests(unittest.TestCase):
    def test_intent_requires_confirmation_then_reaches_execution_gate(self):
        pipeline = SharedAutonomyPipeline(gate=IntentGate(stable_frames=2),
                                          network=NetworkSimulator(latency_ms=20))
        point = (JointPoint(0, (0, -1, 1, -1, 0, 0)),
                 JointPoint(1, (0.1, -1.1, 1.1, -1.1, 0, 0)))
        intent = lambda timestamp: HandIntent(0.5, 0.5, 0.95, timestamp, track_id=1)
        self.assertEqual(pipeline.handle_intent(intent(0), now_ms=0, legal_cells={4}, trajectory=point, deadline_ms=100).stage, "perception")
        result = pipeline.handle_intent(intent(1), now_ms=1, legal_cells={4}, trajectory=point, deadline_ms=100)
        self.assertEqual((result.status, result.stage, result.cell), ("ready", "execution", 4))

    def test_pipeline_records_transport_delivery_latency(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = TelemetryRecorder(Path(directory) / "events.jsonl")
            pipeline = SharedAutonomyPipeline(
                gate=IntentGate(stable_frames=1),
                network=NetworkSimulator(latency_ms=20),
                telemetry=recorder,
            )
            result = pipeline.handle_intent(
                HandIntent(0.5, 0.5, 0.95, 10), now_ms=10, legal_cells={4},
                trajectory=(JointPoint(0, (0, -1, 1, -1, 0, 0)),), deadline_ms=40,
            )
            self.assertEqual(result.status, "ready")
            self.assertEqual(recorder.summary()["transport_latency_p95_ms"], 20.0)

    def test_pipeline_rejects_network_deadline(self):
        pipeline = SharedAutonomyPipeline(gate=IntentGate(stable_frames=1),
                                          network=NetworkSimulator(latency_ms=100))
        point = (JointPoint(0, (0, -1, 1, -1, 0, 0)),)
        result = pipeline.handle_intent(HandIntent(0.1, 0.1, 0.95, 0), now_ms=0,
                                        legal_cells={0}, trajectory=point, deadline_ms=50)
        self.assertEqual((result.stage, result.reason), ("transport", "deadline_expired"))
