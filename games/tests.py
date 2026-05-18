import chess
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import GameInvitation
from .views import evaluate_board_outcome, read_analyzer_game, read_internal_coordinate_game


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


class DrawOutcomeTests(SimpleTestCase):
    def test_detects_stalemate(self):
        board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")

        self.assertEqual(evaluate_board_outcome(board)["result"], "draw")

    def test_detects_insufficient_material(self):
        board = chess.Board("8/8/8/8/8/8/4N3/4K2k w - - 0 1")

        self.assertEqual(evaluate_board_outcome(board)["result"], "draw")

    def test_detects_fifty_move_rule(self):
        board = chess.Board("8/8/8/8/8/8/4K3/4R2k w - - 100 1")

        self.assertEqual(evaluate_board_outcome(board)["reason"], "fifty_moves")

    def test_detects_threefold_repetition_claim(self):
        board = chess.Board()

        for move in ["g1f3", "g8f6", "f3g1", "f6g8"] * 2:
            board.push(chess.Move.from_uci(move))

        self.assertEqual(evaluate_board_outcome(board)["reason"], "threefold_repetition")


class InvitationLinkTests(TestCase):
    def test_accepts_link_invitation_and_redirects_to_game(self):
        creator = User.objects.create_user(username="creator", password="pass")
        opponent = User.objects.create_user(username="opponent", password="pass")
        invitation = GameInvitation.objects.create(
            creator=creator,
            opponent_mode="link",
            creator_color="white",
        )

        self.client.force_login(opponent)
        response = self.client.get(reverse("accept_invitation_link", args=[invitation.token]))

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertEqual(invitation.opponent, opponent)
        self.assertIsNotNone(invitation.game)
        self.assertRedirects(response, reverse("game_detail", args=[invitation.game_id]))
