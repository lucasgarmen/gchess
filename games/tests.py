import json
import os
from unittest.mock import patch

import chess
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import ChessGame, GameInvitation, Move
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

    def test_link_invitation_cannot_be_accepted_twice(self):
        creator = User.objects.create_user(username="creator", password="pass")
        first_opponent = User.objects.create_user(username="first", password="pass")
        second_opponent = User.objects.create_user(username="second", password="pass")
        invitation = GameInvitation.objects.create(
            creator=creator,
            opponent_mode="link",
            creator_color="white",
        )

        self.client.force_login(first_opponent)
        first_response = self.client.get(reverse("accept_invitation_link", args=[invitation.token]))

        invitation.refresh_from_db()
        first_game_id = invitation.game_id
        self.assertRedirects(first_response, reverse("game_detail", args=[first_game_id]))

        self.client.force_login(second_opponent)
        second_response = self.client.get(reverse("accept_invitation_link", args=[invitation.token]))

        invitation.refresh_from_db()
        self.assertEqual(invitation.opponent, first_opponent)
        self.assertEqual(invitation.game_id, first_game_id)
        self.assertEqual(ChessGame.objects.count(), 1)
        self.assertRedirects(second_response, reverse("games_list"))


class GameAccessTests(TestCase):
    def test_user_cannot_access_other_users_game(self):
        owner = User.objects.create_user(username="owner", password="pass")
        intruder = User.objects.create_user(username="intruder", password="pass")
        game = ChessGame.objects.create(
            owner=owner,
            white_user=owner,
            white_player=owner.username,
            black_player="Guest",
        )

        self.client.force_login(intruder)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_move_opponents_piece(self):
        white = User.objects.create_user(username="white", password="pass")
        black = User.objects.create_user(username="black", password="pass")
        game = ChessGame.objects.create(
            owner=white,
            white_user=white,
            black_user=black,
            white_player=white.username,
            black_player=black.username,
        )
        Move.objects.create(
            game=game,
            move_number=1,
            from_square="e2",
            to_square="e4",
            piece_type="pawn",
            piece_color="white",
        )

        self.client.force_login(white)
        response = self.client.post(
            reverse("save_move", args=[game.id]),
            data=json.dumps({
                "from": "e7",
                "to": "e5",
                "piece_color": "white",
                "piece_type": "pawn",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(game.moves.count(), 1)

    def test_server_does_not_trust_client_piece_color_for_legal_move(self):
        white = User.objects.create_user(username="white", password="pass")
        black = User.objects.create_user(username="black", password="pass")
        game = ChessGame.objects.create(
            owner=white,
            white_user=white,
            black_user=black,
            white_player=white.username,
            black_player=black.username,
        )

        self.client.force_login(white)
        response = self.client.post(
            reverse("save_move", args=[game.id]),
            data=json.dumps({
                "from": "e2",
                "to": "e4",
                "piece_color": "black",
                "piece_type": "pawn",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        move = game.moves.get()
        self.assertEqual(move.piece_color, "white")

    def test_invalid_pgn_does_not_break_analyzer(self):
        user = User.objects.create_user(username="player", password="pass")

        self.client.force_login(user)
        response = self.client.post(reverse("game_analyzer"), data={"pgn": "this is not pgn"})

        self.assertEqual(response.status_code, 200)

    def test_missing_stockfish_returns_clear_engine_error(self):
        user = User.objects.create_user(username="stockfish-user", password="pass")

        self.client.force_login(user)

        with patch.dict(os.environ, {"STOCKFISH_PATH": r"C:\missing\stockfish.exe"}), patch("games.views.shutil.which", return_value=None):
            response = self.client.post(
                reverse("engine_move"),
                data=json.dumps({"moves": [], "elo": 1320}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("Stockfish is not available", response.json()["error"])
