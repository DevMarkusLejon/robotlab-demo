"""Tests of geometric contracts and simulation-only state transitions."""

import json
import math
import unittest

from robotlab.robot import BoardGeometry, CartesianPoint, SimulatedRobot


class GeometryTests(unittest.TestCase):
    def assertPoint(self, point, expected):
        for actual, value in zip((point.x_m, point.y_m, point.z_m), expected):
            self.assertAlmostEqual(actual, value)

    def test_cells_are_centres_with_one_cell_step_vectors(self):
        board = BoardGeometry()
        for cell in range(9):
            row, column = divmod(cell, 3)
            self.assertPoint(board.cell_center(cell), ((column + 0.5) * 0.05, (row + 0.5) * 0.05, 0))

    def test_rotated_and_translated_board_uses_its_normal(self):
        board = BoardGeometry((1, 2, 3), (0, 0, 0.1), (0.2, 0, 0), clearance_m=0.04)
        plan = board.plan_placement(5, "O")
        self.assertPoint(plan.target, (1.3, 2, 3.25))
        self.assertPoint(plan.approach, (1.3, 2.04, 3.25))
        self.assertEqual(plan.retract, plan.approach)
        self.assertEqual((plan.cell, plan.symbol), (5, "O"))

    def test_tilted_board_clearance_is_perpendicular_and_has_requested_length(self):
        board = BoardGeometry((0.3, -0.2, 0.4), (0.04, 0.04, 0), (0, 0, 0.06), 0.07)
        plan = board.plan_placement(8, "X")
        offset = tuple(a - b for a, b in zip(plan.approach.to_dict().values(), plan.target.to_dict().values()))
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in offset)), 0.07)
        self.assertAlmostEqual(sum(a * b for a, b in zip(offset, board.column_step_m)), 0)
        self.assertAlmostEqual(sum(a * b for a, b in zip(offset, board.row_step_m)), 0)
        self.assertGreater(offset[0], 0)
        self.assertLess(offset[1], 0)

    def test_rejects_invalid_calibration(self):
        cases = [
            {"origin_m": (0, 0)},
            {"origin_m": "000"},
            {"origin_m": (True, 0, 0)},
            {"origin_m": (float("nan"), 0, 0)},
            {"origin_m": (0, float("inf"), 0)},
            {"origin_m": (10 ** 400, 0, 0)},
            {"column_step_m": (0, 0, 0)},
            {"column_step_m": (0.05, 0, 0), "row_step_m": (0.1, 0, 0)},
            {"row_step_m": (0.01, 0.05, 0)},
            {"column_step_m": (1e-9, 0, 0)},
            {"column_step_m": (11, 0, 0)},
            {"column_step_m": (1e300, 0, 0)},
            {"clearance_m": True},
            {"clearance_m": float("nan")},
            {"clearance_m": float("inf")},
            {"clearance_m": -0.1},
            {"clearance_m": 0},
            {"clearance_m": 11},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                BoardGeometry(**arguments)

    def test_list_input_becomes_immutable_coordinates(self):
        origin = [0, 0, 0]
        board = BoardGeometry(origin_m=origin)
        origin[0] = 99
        self.assertEqual(board.origin_m, (0, 0, 0))

    def test_rejects_non_integer_cells_and_bad_symbols(self):
        board = BoardGeometry()
        for cell in (-1, 9, True, False, 1.0, "1", None, float("nan")):
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                board.cell_center(cell)
        for symbol in ("x", "", "Y", 1, True, None, []):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                board.plan_placement(0, symbol)

    def test_cartesian_point_rejects_nonfinite_and_boolean_values(self):
        for value in (True, "0", None, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CartesianPoint(value, 0, 0)


class SimulationTests(unittest.TestCase):
    def test_simulation_result_is_explicit_and_json_safe(self):
        robot = SimulatedRobot()
        result = robot.place(4, "X", "first")
        self.assertTrue(robot.simulation_only)
        self.assertEqual(result["status"], "simulated")
        self.assertIs(result["simulation_only"], True)
        self.assertEqual(result["plan"]["cell"], 4)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertEqual(robot.executed, [result])

    def test_stop_latches_even_for_an_existing_command_until_reset(self):
        robot = SimulatedRobot()
        robot.place(0, "X", "first")
        self.assertEqual(robot.stop()["status"], "stopped")
        robot.stop()
        self.assertTrue(robot.stopped)
        for command in ("first", "second"):
            with self.subTest(command=command), self.assertRaises(RuntimeError):
                robot.place(0, "X", command)
        self.assertEqual(len(robot.executed), 1)
        self.assertEqual(robot.reset()["status"], "ready")
        self.assertFalse(robot.stopped)
        self.assertEqual(robot.executed, [])
        self.assertEqual(robot.place(2, "O", "first")["plan"]["cell"], 2)

    def test_retry_is_idempotent_and_conflicting_id_is_rejected(self):
        robot = SimulatedRobot()
        first = robot.place(0, "X", "request-1")
        self.assertEqual(robot.place(0, "X", "request-1"), first)
        self.assertEqual(len(robot.executed), 1)
        for cell, symbol in ((1, "X"), (0, "O")):
            with self.subTest(cell=cell, symbol=symbol), self.assertRaises(ValueError):
                robot.place(cell, symbol, "request-1")

    def test_callers_cannot_mutate_recorded_results(self):
        robot = SimulatedRobot()
        result = robot.place(0, "O", "one")
        result["plan"]["cell"] = 8
        history = robot.executed
        history[0]["plan"]["cell"] = 7
        history.clear()
        self.assertEqual(robot.place(0, "O", "one")["plan"]["cell"], 0)
        self.assertEqual(len(robot.executed), 1)

    def test_bad_commands_do_not_change_state(self):
        robot = SimulatedRobot()
        for cell, symbol, command_id in ((True, "X", "one"), (0, "Y", "two"), (0, "X", ""), (0, "X", "  "), (0, "X", 1), (0, "X", "x" * 129)):
            with self.subTest(cell=cell, symbol=symbol, command_id=command_id), self.assertRaises(ValueError):
                robot.place(cell, symbol, command_id)
        self.assertEqual(robot.executed, [])
        self.assertFalse(robot.stopped)


if __name__ == "__main__":
    unittest.main()
