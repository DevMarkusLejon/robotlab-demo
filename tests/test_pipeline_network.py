import unittest

from robotlab.intent import HandIntent, IntentGate
from robotlab.network import NetworkSimulator
from robotlab.pipeline import SharedAutonomyPipeline
from robotlab.safety import JointPoint


class NetworkTests(unittest.TestCase):
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

    def test_pipeline_rejects_network_deadline(self):
        pipeline = SharedAutonomyPipeline(gate=IntentGate(stable_frames=1),
                                          network=NetworkSimulator(latency_ms=100))
        point = (JointPoint(0, (0, -1, 1, -1, 0, 0)),)
        result = pipeline.handle_intent(HandIntent(0.1, 0.1, 0.95, 0), now_ms=0,
                                        legal_cells={0}, trajectory=point, deadline_ms=50)
        self.assertEqual((result.stage, result.reason), ("transport", "deadline_expired"))
