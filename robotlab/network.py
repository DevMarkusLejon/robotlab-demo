"""Deterministic network impairment model for remote-operation tests."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    delivered_at_ms: int
    reason: str


class NetworkSimulator:
    """Model latency, jitter and loss without sleeping in tests or demos."""

    def __init__(self, *, latency_ms: int = 80, jitter_ms: int = 0,
                 drop_rate: float = 0.0, seed: int = 0) -> None:
        if type(latency_ms) is not int or latency_ms < 0:
            raise ValueError("latency_ms must be a nonnegative integer")
        if type(jitter_ms) is not int or jitter_ms < 0:
            raise ValueError("jitter_ms must be a nonnegative integer")
        if not 0 <= drop_rate <= 1:
            raise ValueError("drop_rate must be in [0, 1]")
        self.latency_ms = latency_ms
        self.jitter_ms = jitter_ms
        self.drop_rate = drop_rate
        self._random = random.Random(seed)

    def deliver(self, payload: Any, *, sent_at_ms: int, deadline_ms: int) -> DeliveryResult:
        del payload  # The simulator models transport properties, not serialization.
        if type(sent_at_ms) is not int or type(deadline_ms) is not int or sent_at_ms < 0:
            raise ValueError("timestamps must be nonnegative integers")
        if deadline_ms < sent_at_ms:
            raise ValueError("deadline must be at or after sent_at_ms")
        if self._random.random() < self.drop_rate:
            return DeliveryResult(False, sent_at_ms, "packet_loss")
        jitter = self._random.randint(-self.jitter_ms, self.jitter_ms) if self.jitter_ms else 0
        arrival = sent_at_ms + max(0, self.latency_ms + jitter)
        if arrival > deadline_ms:
            return DeliveryResult(False, arrival, "deadline_expired")
        return DeliveryResult(True, arrival, "delivered")
