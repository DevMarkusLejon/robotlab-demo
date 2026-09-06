"""Exhaustive rule and opponent checks using only the Python standard library."""

from dataclasses import FrozenInstanceError
from functools import lru_cache
from itertools import product
import unittest

from robotlab.game import Board, choose_move


# Kept independent of the implementation to check its state validation.
_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def reference_winner(cells: tuple[str, ...]) -> str | None:
    for player in ("X", "O"):
        if any(all(cells[index] == player for index in line) for line in _LINES):
            return player
    return None


def reachable_states() -> set[tuple[str, ...]]:
    """Enumerate forward from an empty board, stopping at every terminal state."""
    states: set[tuple[str, ...]] = set()

    def visit(cells: tuple[str, ...], player: str) -> None:
        if cells in states:
            return
        states.add(cells)
        if reference_winner(cells) is not None or "" not in cells:
            return
        for index, value in enumerate(cells):
            if not value:
                child = cells[:index] + (player,) + cells[index + 1 :]
                visit(child, "O" if player == "X" else "X")

    visit(("",) * 9, "X")
    return states


@lru_cache(maxsize=None)
def reference_outcome(cells: tuple[str, ...]) -> int:
    """Independent tuple-based solver, scored from X's perspective."""
    winner = reference_winner(cells)
    if winner:
        return 1 if winner == "X" else -1
    if "" not in cells:
        return 0
    player = "X" if cells.count("X") == cells.count("O") else "O"
    results = [
        reference_outcome(cells[:index] + (player,) + cells[index + 1 :])
        for index, value in enumerate(cells)
        if not value
    ]
    return max(results) if player == "X" else min(results)


class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.states = reachable_states()

    def test_empty_board_and_immutable_moves(self) -> None:
        board = Board()
        self.assertEqual(board.next_player, "X")
        self.assertIsNone(board.winner)
        self.assertFalse(board.is_draw)
        self.assertEqual(board.legal_moves, tuple(range(9)))
        moved = board.play(4)
        self.assertEqual(moved.cells, ("", "", "", "", "X", "", "", "", ""))
        self.assertEqual(moved.next_player, "O")
        self.assertEqual(board, Board())
        self.assertEqual(hash(board), hash(Board()))
        with self.assertRaises(FrozenInstanceError):
            board.cells = moved.cells

    def test_rejects_malformed_board_data(self) -> None:
        invalid = (
            None,
            [""] * 9,
            "XXXXXXXXX",
            ("",) * 8,
            ("",) * 10,
            ("x",) + ("",) * 8,
            (" ",) + ("",) * 8,
            (None,) + ("",) * 8,
            (True,) + ("",) * 8,
            ([],) + ("",) * 8,
        )
        for cells in invalid:
            with self.subTest(cells=cells), self.assertRaises(ValueError):
                Board(cells)

    def test_rejects_invalid_move_types_and_indices(self) -> None:
        for cell in (True, False, -1, 9, 100, 1.0, "1", None, [], {}):
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                Board().play(cell)

    def test_rejects_occupied_cells(self) -> None:
        with self.assertRaisesRegex(ValueError, "occupied"):
            Board().play(0).play(0)

    def test_wins_draws_and_terminal_moves(self) -> None:
        boards = (
            (Board(("X", "X", "X", "O", "O", "", "", "", "")), "X", False),
            (Board(("X", "X", "", "O", "O", "O", "X", "", "")), "O", False),
            (Board(("X", "O", "X", "X", "O", "O", "O", "X", "X")), None, True),
        )
        for board, winner, is_draw in boards:
            with self.subTest(board=board):
                self.assertEqual(board.winner, winner)
                self.assertEqual(board.is_draw, is_draw)
                self.assertIsNone(board.next_player)
                self.assertEqual(board.legal_moves, ())
                with self.assertRaisesRegex(ValueError, "ended"):
                    board.play(8)
                with self.assertRaisesRegex(ValueError, "ended"):
                    choose_move(board)

    def test_validation_accepts_exactly_all_reachable_states(self) -> None:
        self.assertEqual(len(self.states), 5478)
        for cells in product(("", "X", "O"), repeat=9):
            if cells in self.states:
                self.assertEqual(Board(cells).cells, cells)
            else:
                with self.subTest(cells=cells), self.assertRaises(ValueError):
                    Board(cells)

    def test_rules_are_consistent_for_every_reachable_state(self) -> None:
        for cells in self.states:
            board = Board(cells)
            winner = reference_winner(cells)
            terminal = winner is not None or "" not in cells
            player = "X" if cells.count("X") == cells.count("O") else "O"
            expected_moves = () if terminal else tuple(
                index for index, value in enumerate(cells) if not value
            )
            with self.subTest(cells=cells):
                self.assertEqual(board.winner, winner)
                self.assertEqual(board.is_draw, winner is None and "" not in cells)
                self.assertEqual(board.next_player, None if terminal else player)
                self.assertEqual(board.legal_moves, expected_moves)
                for move in expected_moves:
                    child = board.play(move)
                    self.assertIn(child.cells, self.states)
                    self.assertEqual(child.cells[move], player)
                    self.assertEqual(
                        sum(a != b for a, b in zip(cells, child.cells)), 1
                    )


class BotTests(unittest.TestCase):
    def test_deterministic_opening_and_input_validation(self) -> None:
        self.assertEqual(choose_move(Board()), 0)
        self.assertEqual(choose_move(Board()), 0)
        for value in (None, ("",) * 9, {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                choose_move(value)

    def test_takes_forced_win_and_blocks_forced_loss(self) -> None:
        cases = (
            (("X", "X", "", "O", "O", "", "", "", ""), 2),
            (("O", "O", "", "X", "", "X", "X", "", ""), 2),
            (("O", "O", "", "X", "", "", "X", "", ""), 2),
            (("X", "X", "", "O", "", "", "", "", ""), 2),
        )
        for cells, move in cases:
            with self.subTest(cells=cells):
                self.assertEqual(choose_move(Board(cells)), move)

    def test_every_reachable_choice_is_optimal_and_ties_use_lowest_index(self) -> None:
        for cells in reachable_states():
            board = Board(cells)
            if board.next_player is None:
                continue
            desired_outcome = reference_outcome(cells)
            best_moves = [
                cell for cell in board.legal_moves
                if reference_outcome(board.play(cell).cells) == desired_outcome
            ]
            with self.subTest(cells=cells):
                self.assertEqual(choose_move(board), min(best_moves))

    def test_bot_cannot_lose_as_either_player_against_any_opponent(self) -> None:
        for bot in ("X", "O"):
            visited: set[Board] = set()
            terminal_count = 0

            def visit(board: Board) -> None:
                nonlocal terminal_count
                if board in visited:
                    return
                visited.add(board)
                if board.next_player is None:
                    terminal_count += 1
                    self.assertIn(board.winner, (None, bot), (bot, board))
                    return
                moves = (choose_move(board),) if board.next_player == bot else board.legal_moves
                for cell in moves:
                    visit(board.play(cell))

            with self.subTest(bot=bot):
                visit(Board())
                self.assertGreater(terminal_count, 0)


if __name__ == "__main__":
    unittest.main()
