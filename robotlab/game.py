"""Immutable tic-tac-toe rules and an optimal, deterministic opponent.

Cells are numbered 0 through 8 in row-major order. X always moves first.
This module has no hardware or third-party dependencies.
"""

from dataclasses import dataclass
from functools import lru_cache


_WINNING_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def _winners(cells: tuple[str, ...]) -> frozenset[str]:
    return frozenset(
        cells[a]
        for a, b, c in _WINNING_LINES
        if cells[a] and cells[a] == cells[b] == cells[c]
    )


@lru_cache(maxsize=None)
def _is_reachable(cells: tuple[str, ...]) -> bool:
    """Find a legal predecessor, never stepping back through an earlier win."""
    x_count, o_count = cells.count("X"), cells.count("O")
    if x_count not in (o_count, o_count + 1):
        return False
    winners = _winners(cells)
    if len(winners) > 1:
        return False
    if "X" in winners and x_count != o_count + 1:
        return False
    if "O" in winners and x_count != o_count:
        return False
    if x_count == o_count == 0:
        return True

    last_player = "X" if x_count > o_count else "O"
    for cell, player in enumerate(cells):
        if player == last_player:
            previous = cells[:cell] + ("",) + cells[cell + 1 :]
            if not _winners(previous) and _is_reachable(previous):
                return True
    return False


@dataclass(frozen=True)
class Board:
    """A reachable board state; empty cells are represented by ``""``.

    Invalid data raises ValueError. A tuple is required so a board remains
    immutable and safe to use as a cache key.
    """

    cells: tuple[str, ...] = ("",) * 9

    def __post_init__(self) -> None:
        if not isinstance(self.cells, tuple):
            raise ValueError("cells must be a tuple of nine strings.")
        if len(self.cells) != 9:
            raise ValueError("cells must contain exactly nine entries.")
        if any(
            not isinstance(value, str) or value not in ("", "X", "O")
            for value in self.cells
        ):
            raise ValueError('Each cell must be "", "X", or "O".')
        if not _is_reachable(self.cells):
            raise ValueError(
                "Board is unreachable: X starts, players alternate, "
                "and the game stops at the first win."
            )

    @property
    def winner(self) -> str | None:
        """The winning player, or None if neither player has won."""
        return next(iter(_winners(self.cells)), None)

    @property
    def is_draw(self) -> bool:
        """Whether the board is full without a winner."""
        return "" not in self.cells and self.winner is None

    @property
    def next_player(self) -> str | None:
        """The player to move, or None when the game has ended."""
        if self.winner is not None or "" not in self.cells:
            return None
        return "X" if self.cells.count("X") == self.cells.count("O") else "O"

    @property
    def legal_moves(self) -> tuple[int, ...]:
        """Available cell indices in ascending order; empty after game over."""
        if self.next_player is None:
            return ()
        return tuple(cell for cell, value in enumerate(self.cells) if not value)

    def play(self, cell: int) -> "Board":
        """Return a new board after one move, raising ValueError if invalid."""
        if isinstance(cell, bool) or not isinstance(cell, int):
            raise ValueError("cell must be an integer from 0 through 8.")
        if not 0 <= cell < 9:
            raise ValueError("cell must be an integer from 0 through 8.")
        player = self.next_player
        if player is None:
            raise ValueError("Cannot play after the game has ended.")
        if self.cells[cell]:
            raise ValueError(f"Cell {cell} is already occupied.")
        return Board(self.cells[:cell] + (player,) + self.cells[cell + 1 :])


@lru_cache(maxsize=None)
def _minimax_score(board: Board) -> int:
    """Score optimal play from X's perspective: win 1, draw 0, loss -1."""
    winner = board.winner
    if winner is not None:
        return 1 if winner == "X" else -1
    if board.is_draw:
        return 0
    scores = (_minimax_score(board.play(cell)) for cell in board.legal_moves)
    return max(scores) if board.next_player == "X" else min(scores)


def choose_move(board: Board) -> int:
    """Choose an optimal move, breaking ties by lowest cell index.

    Raises ValueError for a terminal board or an argument that is not a Board.
    The supplied board is never modified.
    """
    if not isinstance(board, Board):
        raise ValueError("board must be a Board instance.")
    if board.next_player is None:
        raise ValueError("Cannot choose a move after the game has ended.")
    select = max if board.next_player == "X" else min
    return select(board.legal_moves, key=lambda cell: _minimax_score(board.play(cell)))
