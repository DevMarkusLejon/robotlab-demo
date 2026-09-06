"""Versioned, in-memory command handling for a single simulated game."""

from copy import deepcopy
from dataclasses import dataclass
import json
import re
from threading import RLock
import time
from uuid import uuid4

from .game import Board, choose_move
from .robot import SimulatedRobot


@dataclass
class CommandError(Exception):
    code: str
    message: str
    status: int = 400

    def __str__(self):
        return self.message


def now_ms():
    return time.time_ns() // 1_000_000


def make_command(state, action, *, cell=None, command_id=None, clock=now_ms):
    """Build a command using the state most recently read from the server."""
    command = {
        "protocol_version": 1,
        "command_id": command_id or str(uuid4()),
        "session_id": state["session_id"],
        "expected_revision": state["revision"],
        "expires_at_ms": clock() + 10_000,
        "action": action,
    }
    if cell is not None:
        command["cell"] = cell
    return command


class Session:
    """Remote player is X, robot opponent is O. Both placements are simulated.

    Commands and receipts survive only for this process. Never use the receipt
    cache as a durable exactly-once guarantee for physical hardware.
    """

    def __init__(self, *, robot=None, clock=now_ms, max_receipts=1024):
        if type(max_receipts) is not int or max_receipts < 1:
            raise ValueError("max_receipts must be a positive integer")
        self.robot = robot if robot is not None else SimulatedRobot()
        self.clock = clock
        self.max_receipts = max_receipts
        self.board = Board()
        self.session_id = str(uuid4())
        self.revision = 0
        self.stopped = False
        self.fault = None
        self._receipts = {}
        self._lock = RLock()

    def state(self):
        with self._lock:
            return {
                "protocol_version": 1,
                "simulation_only": True,
                "session_id": self.session_id,
                "revision": self.revision,
                "board": list(self.board.cells),
                "next_player": self.board.next_player,
                "winner": self.board.winner,
                "is_draw": self.board.is_draw,
                "legal_moves": list(self.board.legal_moves),
                "stopped": self.stopped,
                "fault": self.fault,
                "server_time_ms": self.clock(),
            }

    @staticmethod
    def _validate(command):
        if not isinstance(command, dict):
            raise CommandError("invalid_command", "Command must be a JSON object")
        required = {"protocol_version", "command_id", "session_id", "expected_revision",
                    "expires_at_ms", "action"}
        allowed = required | ({"cell"} if command.get("action") == "move" else set())
        if set(command) != allowed:
            raise CommandError("invalid_command", "Missing or unexpected command fields")
        if type(command["protocol_version"]) is not int or command["protocol_version"] != 1:
            raise CommandError("protocol_version", "Only protocol version 1 is supported")
        if not isinstance(command["command_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", command["command_id"]
        ):
            raise CommandError("invalid_command", "command_id must be 1-64 letters, digits, _ or -")
        if not isinstance(command["session_id"], str) or not 1 <= len(command["session_id"]) <= 64:
            raise CommandError("invalid_command", "Invalid session_id")
        for name in ("expected_revision", "expires_at_ms"):
            if type(command[name]) is not int or not 0 <= command[name] <= 2**53 - 1:
                raise CommandError("invalid_command", f"{name} must be a nonnegative safe integer")
        if command["action"] not in ("move", "robot_move", "stop", "reset"):
            raise CommandError("invalid_command", "Unknown action")
        if command["action"] == "move" and (
            type(command["cell"]) is not int or not 0 <= command["cell"] <= 8
        ):
            raise CommandError("invalid_command", "cell must be an integer from 0 to 8")

    def submit(self, command):
        with self._lock:
            self._validate(command)
            fingerprint = json.dumps(command, sort_keys=True, separators=(",", ":"))
            command_id = command["command_id"]
            receipt = self._receipts.get(command_id)
            if receipt:
                if receipt[0] != fingerprint:
                    raise CommandError("id_conflict", "command_id was already used with another payload", 409)
                return {"duplicate": True, "result": deepcopy(receipt[1]), "state": self.state()}
            if command["session_id"] != self.session_id:
                raise CommandError("session_conflict", "Read current state: session changed", 409)
            action = command["action"]
            # A stop for this session remains useful even if state/time moved on.
            if action != "stop":
                if command["expected_revision"] != self.revision:
                    raise CommandError("revision_conflict", "Read current state: revision changed", 409)
                remaining = command["expires_at_ms"] - self.clock()
                if remaining <= 0:
                    raise CommandError("expired", "Command deadline has passed", 408)
                if remaining > 30_000:
                    raise CommandError("invalid_deadline", "Deadline must be within 30 seconds of server time")
                if len(self._receipts) >= self.max_receipts:
                    raise CommandError("receipt_capacity", "Receipt cache full; restart simulator", 503)

            result = {"command_id": command_id, "action": action, "status": "simulated"}
            if action == "stop":
                self.robot.stop()
                if not self.stopped:
                    self.stopped = True
                    self.revision += 1
                result["status"] = "stopped"
            elif action == "reset":
                self.robot.reset()
                self.board = Board()
                self.session_id = str(uuid4())
                self.revision = 0
                self.stopped = False
                self.fault = None
                result["status"] = "reset"
            else:
                if self.stopped:
                    raise CommandError("stopped", "Simulator is stopped; reset before continuing", 409)
                if self.board.next_player is None:
                    raise CommandError("game_over", "Game has ended; reset to start again", 409)
                symbol = "X" if action == "move" else "O"
                if self.board.next_player != symbol:
                    raise CommandError("wrong_turn", f"It is {self.board.next_player}'s turn", 409)
                cell = command["cell"] if action == "move" else choose_move(self.board)
                try:
                    next_board = self.board.play(cell)
                except ValueError as exc:
                    raise CommandError("invalid_move", str(exc), 409) from exc
                try:
                    result["placement"] = self.robot.place(cell, symbol, command_id)
                except Exception:
                    # Do not blindly retry an action whose outcome is uncertain.
                    self.stopped = True
                    self.fault = "placement_failed"
                    result["status"] = "fault"
                    result["error"] = self.fault
                    try:
                        self.robot.stop()
                    except Exception:
                        pass
                else:
                    self.board = next_board
                    result.update(cell=cell, symbol=symbol)
                self.revision += 1
            result.update(session_id=self.session_id, revision=self.revision)
            # Stops still work when the bounded cache is full; their effect is
            # inherently idempotent. All other accepted commands retain receipts.
            if len(self._receipts) < self.max_receipts:
                self._receipts[command_id] = (fingerprint, deepcopy(result))
            return {"duplicate": False, "result": deepcopy(result), "state": self.state()}
