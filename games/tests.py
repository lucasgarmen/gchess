import chess
from django.test import SimpleTestCase

from .views import read_analyzer_game, read_internal_coordinate_game


class AnalyzerPgnParsingTests(SimpleTestCase):
    def test_reads_internal_coordinate_moves(self):
        game, error = read_internal_coordinate_game(
            "\n".join([
                "1. e2 -> e4",
                "2. f7 -> f5",
                "3. e4 -> f5",
                "4. e7 -> e6",
                "5. f5 -> f6",
            ])
        )

        self.assertIsNone(error)
        self.assertEqual(
            [move.uci() for move in game.mainline_moves()],
            ["e2e4", "f7f5", "e4f5", "e7e6", "f5f6"],
        )

    def test_reads_standard_pgn_still(self):
        game, error = read_analyzer_game("1. e4 f5 2. exf5 e6 3. f6")

        self.assertIsNone(error)
        board = chess.Board()
        san_moves = []
        for move in game.mainline_moves():
            san_moves.append(board.san(move))
            board.push(move)

        self.assertEqual(san_moves, ["e4", "f5", "exf5", "e6", "f6"])
