"""Shared-autonomy pipeline joining intent, transport and safety gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .intent import HandIntent, IntentGate
from .network import NetworkSimulator
from .safety import JointPoint, validate_trajectory
from .telemetry import TelemetryRecorder


@dataclass(frozen=True)
class PipelineResult:
    status: str
    stage: str
    cell: int | None
    reason: str


class SharedAutonomyPipeline:
    """Make every command pass perception, transport and motion gates."""

    def __init__(self, *, gate: IntentGate | None = None,
                 network: NetworkSimulator | None = None,
                 telemetry: TelemetryRecorder | None = None) -> None:
        self.gate = gate or IntentGate()
        self.network = network or NetworkSimulator()
        self.telemetry = telemetry

    def _record(self, event: str, **fields: object) -> None:
        if self.telemetry:
            self.telemetry.record(event, **fields)

    def handle_intent(self, intent: HandIntent, *, now_ms: int, legal_cells: set[int],
                      trajectory: Iterable[JointPoint], deadline_ms: int) -> PipelineResult:
        decision = self.gate.update(intent, now_ms=now_ms, legal_cells=legal_cells)
        self._record("intent_seen", cell=decision.cell, status=decision.status,
                     reason=decision.reason, confidence=decision.confidence)
        if decision.status != "accepted":
            return PipelineResult(decision.status, "perception", decision.cell, decision.reason)
        self._record("intent_accepted", cell=decision.cell)
        delivery = self.network.deliver({"cell": decision.cell}, sent_at_ms=now_ms,
                                        deadline_ms=deadline_ms)
        if not delivery.delivered:
            self._record("transport_rejected", cell=decision.cell, reason=delivery.reason,
                         delivered_at_ms=delivery.delivered_at_ms)
            return PipelineResult("rejected", "transport", decision.cell, delivery.reason)
        self._record("transport_delivered", cell=decision.cell,
                     delivered_at_ms=delivery.delivered_at_ms,
                     latency_ms=delivery.delivered_at_ms - now_ms)
        report = validate_trajectory(tuple(trajectory))
        if not report.accepted:
            self._record("safety_rejected", cell=decision.cell, reason=report.reason)
            return PipelineResult("rejected", "safety", decision.cell, report.reason)
        self._record("trajectory_ready", cell=decision.cell,
                     delivered_at_ms=delivery.delivered_at_ms,
                     max_speed_rad_s=report.max_speed_rad_s)
        return PipelineResult("ready", "execution", decision.cell, "trajectory_ready")
