"""Game state is committed only from an independently verified placement."""
from dataclasses import dataclass
from .game import Board, choose_move


@dataclass(frozen=True)
class VerifiedPlacement:
    cell: int
    symbol: str
    cells: tuple
    frame_id: str
    source: str
    confirming_frames: int


class VerifiedMatch:
    def __init__(self, *, source='gazebo_rendered_camera'):
        if source not in ('gazebo_rendered_camera', 'physical_board_camera', 'offline_fixture'):
            raise ValueError('unsupported_placement_source')
        self.source = source
        self.board = Board()
        self.used_frames = set()

    @property
    def token_id(self):
        count = sum(bool(cell) for cell in self.board.cells)
        return 'token' if count == 0 else f'token_{count}'

    def commit(self, receipt, cell):
        expected = self.board.play(cell)
        if (not isinstance(receipt, VerifiedPlacement) or receipt.cell != cell or
                receipt.symbol != self.board.next_player or
                tuple(value or '' for value in receipt.cells) != expected.cells or
                receipt.source != self.source or
                not receipt.frame_id or receipt.frame_id in self.used_frames or
                receipt.confirming_frames < 3):
            raise ValueError('placement_receipt_mismatch')
        self.board = expected
        self.used_frames.add(receipt.frame_id)

    def robot_move(self):
        if self.board.next_player != 'O':
            raise ValueError('not_robot_turn')
        return choose_move(self.board)
