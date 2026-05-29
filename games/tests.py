import json
import os
from unittest.mock import patch

import chess
import chess.engine
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from .models import ChessGame, DailyVisit, GameInvitation, Move
from .views import build_automatic_move_context, build_pgn_from_saved_game, evaluate_board_outcome, generate_comment, read_analyzer_game, read_internal_coordinate_game


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


class SavedGamePgnTests(TestCase):
    def test_builds_standard_pgn_from_saved_finished_game(self):
        white = User.objects.create_user(username="white-pgn", password="pass")
        black = User.objects.create_user(username="black-pgn", password="pass")
        game = ChessGame.objects.create(
            owner=white,
            white_user=white,
            black_user=black,
            white_player=white.username,
            black_player=black.username,
            status="finished",
            result="white",
        )
        Move.objects.create(game=game, move_number=1, from_square="e2", to_square="e4", piece_type="pawn", piece_color="white")
        Move.objects.create(game=game, move_number=2, from_square="e7", to_square="e5", piece_type="pawn", piece_color="black")

        pgn_text = build_pgn_from_saved_game(game)
        parsed_game, error = read_analyzer_game(pgn_text)

        self.assertIsNone(error)
        self.assertIn('[White "white-pgn"]', pgn_text)
        self.assertIn('[Black "black-pgn"]', pgn_text)
        self.assertIn('[Result "1-0"]', pgn_text)
        self.assertEqual([move.uci() for move in parsed_game.mainline_moves()], ["e2e4", "e7e5"])


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


def fake_engine_analysis(cp=None, pv=None, mate=None):
    score = chess.engine.Mate(mate) if mate is not None else chess.engine.Cp(cp or 0)
    return {
        "score": chess.engine.PovScore(score, chess.WHITE),
        "pv": pv or [],
    }


class FakeAnalysisEngine:
    def __init__(self, responses):
        self.responses = responses

    def analyse(self, board, _limit):
        return self.responses.get(board.fen(), fake_engine_analysis(0))

    def quit(self):
        pass


class AutomaticCommentaryTests(SimpleTestCase):
    def build_context(self, played_uci, best_uci, played_cp, best_cp, before_cp=0, language="en"):
        board = chess.Board()
        played_move = chess.Move.from_uci(played_uci)
        best_move = chess.Move.from_uci(best_uci)
        played_board = board.copy()
        played_board.push(played_move)
        best_board = board.copy()
        best_board.push(best_move)
        responses = {
            board.fen(): fake_engine_analysis(before_cp, [best_move]),
            played_board.fen(): fake_engine_analysis(played_cp),
            best_board.fen(): fake_engine_analysis(best_cp),
        }

        return build_automatic_move_context(
            FakeAnalysisEngine(responses),
            board,
            played_move,
            move_number=1,
            language=language,
        )

    def test_e2e4_best_move_is_not_marked_as_inaccuracy(self):
        context = self.build_context("e2e4", "e2e4", played_cp=25, best_cp=25)

        self.assertEqual(context["classification"], "best")
        self.assertEqual(context["centipawn_loss"], 0)
        self.assertEqual(context["played_move_uci"], context["best_move_uci"])
        self.assertNotIn("Inaccuracy", context["comment"])

    def test_played_move_equal_to_best_move_never_recommends_same_move(self):
        context = self.build_context("e2e4", "e2e4", played_cp=-80, best_cp=-80)

        self.assertEqual(context["classification"], "best")
        self.assertNotIn("Better was", context["comment"])

    def test_small_centipawn_loss_is_not_classified_as_bad(self):
        context = self.build_context("d2d4", "e2e4", played_cp=10, best_cp=45)

        self.assertIn(context["classification"], {"book", "good", "normal"})
        self.assertNotIn(context["classification"], {"inaccuracy", "mistake", "blunder"})

    def test_large_centipawn_loss_is_mistake_or_blunder(self):
        mistake = self.build_context("g2g4", "e2e4", played_cp=-170, best_cp=45)
        blunder = self.build_context("g2g4", "e2e4", played_cp=-320, best_cp=45)

        self.assertEqual(mistake["classification"], "mistake")
        self.assertEqual(blunder["classification"], "blunder")

    def test_missing_engine_data_returns_neutral_comment(self):
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        after = board.copy()
        after.push(move)
        engine = FakeAnalysisEngine({
            board.fen(): {"pv": [move]},
            after.fen(): {},
        })

        context = build_automatic_move_context(engine, board, move, move_number=1, language="en")

        self.assertEqual(context["classification"], "neutral")
        self.assertIsNone(context["centipawn_loss"])
        self.assertIn("engine data was incomplete", context["comment"])


class InvitationLinkTests(TestCase):
    def test_named_game_routes_use_english_urls(self):
        self.assertEqual(reverse("games_list"), "/games/")
        self.assertEqual(reverse("game_create"), "/games/new/")
        self.assertEqual(reverse("game_detail", args=[12]), "/games/12/")
        self.assertEqual(reverse("game_analyzer"), "/analyze/")
        self.assertEqual(reverse("set_language"), "/language/")

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
    def create_multiplayer_game(self):
        white = User.objects.create_user(username="white", password="pass")
        black = User.objects.create_user(username="black", password="pass")
        game = ChessGame.objects.create(
            owner=white,
            white_user=white,
            black_user=black,
            white_player=white.username,
            black_player=black.username,
        )
        return white, black, game

    def post_move(self, user, game, from_square, to_square, piece_color="white", piece_type="pawn"):
        self.client.force_login(user)
        return self.client.post(
            reverse("save_move", args=[game.id]),
            data=json.dumps({
                "from": from_square,
                "to": to_square,
                "piece_color": piece_color,
                "piece_type": piece_type,
            }),
            content_type="application/json",
        )

    def test_anonymous_user_cannot_view_private_game(self):
        owner = User.objects.create_user(username="owner", password="pass")
        game = ChessGame.objects.create(
            owner=owner,
            white_user=owner,
            white_player=owner.username,
            black_player="Guest",
        )

        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertEqual(response.status_code, 404)

    def test_game_detail_mounts_react_without_replacing_legacy_board(self):
        owner = User.objects.create_user(username="react-owner", password="pass")
        game = ChessGame.objects.create(
            owner=owner,
            white_user=owner,
            white_player=owner.username,
            black_player="Guest",
        )

        self.client.force_login(owner)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertContains(response, 'id="game-detail-react-root"')
        self.assertContains(response, 'id="react-game-context-data"')
        self.assertContains(response, 'games/react/game_detail_app.js')
        self.assertContains(response, 'react-dom')
        self.assertContains(response, 'id="board"')
        self.assertContains(response, 'games/board.js')

    def test_board_supports_right_click_square_marker(self):
        source = open("games/static/games/board.js", encoding="utf-8").read()
        styles = open("games/static/games/style.css", encoding="utf-8").read()

        self.assertIn("let rightClickMarkedSquare = null", source)
        self.assertIn("function markRightClickSquare(square)", source)
        self.assertIn("board.addEventListener('contextmenu', handleBoardContextMenu)", source)
        self.assertIn("document.addEventListener('pointerdown'", source)
        self.assertIn("clearRightClickMarker()", source)
        self.assertIn("clearQueuedMove();", source)
        self.assertIn(".right-click-marked", styles)
        self.assertIn("rgba(28, 126, 214, 0.48)", styles)

    def test_own_draw_offer_shows_reject_button_for_cancel(self):
        source = open("games/static/games/board.js", encoding="utf-8").read()

        self.assertIn("drawOfferText.innerText = uiText('draw_offer_sent'", source)
        self.assertIn("drawOfferActions.hidden = false", source)
        self.assertIn("acceptDrawButton.hidden = true", source)
        self.assertIn("rejectDrawButton.hidden = false", source)

    def test_captured_pieces_are_grouped_by_type(self):
        source = open("games/static/games/board.js", encoding="utf-8").read()
        styles = open("games/static/games/style.css", encoding="utf-8").read()

        self.assertIn("function groupCapturedPieces(pieces)", source)
        self.assertIn("groupElement.classList.add('captured-piece-group')", source)
        self.assertIn("groupElement.dataset.pieceCount = String(group.count)", source)
        self.assertIn(".captured-piece-group", styles)

    def test_finished_game_detail_includes_cancelable_analysis_loading_overlay(self):
        owner = User.objects.create_user(username="analysis-owner", password="pass")
        game = ChessGame.objects.create(
            owner=owner,
            white_user=owner,
            white_player=owner.username,
            black_player="Guest",
            status="finished",
            result="white",
        )

        self.client.force_login(owner)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertContains(response, 'id="analysis-loading-overlay"')
        self.assertContains(response, 'id="cancel-analysis-loading"')
        self.assertContains(response, 'Isso pode levar alguns segundos enquanto revisamos o PGN.')
        self.assertNotContains(response, 'Stockfish revisa')
        self.assertContains(response, 'games/analysis_loading.js')
        self.assertContains(response, "GChessAnalysisLoading.bindLink('analyze-game-button', { navigate: true })")

    def test_analysis_loading_overlay_uses_selected_language(self):
        owner = User.objects.create_user(username="analysis-language-owner", password="pass")
        game = ChessGame.objects.create(
            owner=owner,
            white_user=owner,
            white_player=owner.username,
            black_player="Guest",
            status="finished",
            result="white",
        )

        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.force_login(owner)
        response = self.client.get(reverse("game_detail", args=[game.id]))

        self.assertContains(response, 'Analyzing game')
        self.assertContains(response, 'This may take a few seconds while we review the PGN.')
        self.assertContains(response, 'Cancel review')

    def test_games_list_only_shows_current_users_games(self):
        user = User.objects.create_user(username="list-user", password="pass")
        other = User.objects.create_user(username="other-list-user", password="pass")
        own_game = ChessGame.objects.create(
            owner=user,
            white_user=user,
            white_player=user.username,
            black_player="Guest",
        )
        other_game = ChessGame.objects.create(
            owner=other,
            white_user=other,
            white_player=other.username,
            black_player="Guest",
        )

        self.client.force_login(user)
        response = self.client.get(reverse("games_list"))

        games = [card["game"] for card in response.context["game_cards"]]
        self.assertIn(own_game, games)
        self.assertNotIn(other_game, games)

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

    def test_non_participant_cannot_save_move_by_changing_id(self):
        white, _black, game = self.create_multiplayer_game()
        intruder = User.objects.create_user(username="move-intruder", password="pass")

        response = self.post_move(intruder, game, "e2", "e4")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(game.moves.count(), 0)

    def test_player_can_cancel_own_draw_offer(self):
        white, _black, game = self.create_multiplayer_game()

        self.client.force_login(white)
        offer_response = self.client.post(reverse("offer_draw", args=[game.id]))
        cancel_response = self.client.post(
            reverse("answer_draw_offer", args=[game.id]),
            data=json.dumps({"accepted": False}),
            content_type="application/json",
        )

        game.refresh_from_db()
        self.assertEqual(offer_response.status_code, 200)
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], "cancelled")
        self.assertFalse(cancel_response.json()["draw_offer"]["pending"])
        self.assertEqual(game.draw_offer_by_color, "")

    def test_player_cannot_accept_own_draw_offer(self):
        white, _black, game = self.create_multiplayer_game()

        self.client.force_login(white)
        self.client.post(reverse("offer_draw", args=[game.id]))
        response = self.client.post(
            reverse("answer_draw_offer", args=[game.id]),
            data=json.dumps({"accepted": True}),
            content_type="application/json",
        )

        game.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(game.draw_offer_by_color, "white")

    def test_only_player_on_turn_can_move(self):
        white, black, game = self.create_multiplayer_game()

        black_response = self.post_move(black, game, "e7", "e5", piece_color="black")
        white_response = self.post_move(white, game, "e2", "e4")

        self.assertEqual(black_response.status_code, 403)
        self.assertEqual(white_response.status_code, 200)
        self.assertEqual(game.moves.count(), 1)

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

    def test_user_cannot_modify_finished_game(self):
        white, _black, game = self.create_multiplayer_game()
        game.status = "finished"
        game.result = "draw"
        game.save(update_fields=["status", "result"])

        response = self.post_move(white, game, "e2", "e4")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(game.moves.count(), 0)

    def test_state_endpoint_returns_latest_multiplayer_state(self):
        white, black, game = self.create_multiplayer_game()
        self.assertEqual(self.post_move(white, game, "e2", "e4").status_code, 200)

        self.client.force_login(black)
        response = self.client.get(reverse("game_state", args=[game.id]))
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["fen"], chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1").fen())
        self.assertEqual(data["turn"], "black")
        self.assertEqual(data["move_count"], 1)
        self.assertEqual(data["last_move"]["from"], "e2")
        self.assertEqual(data["last_move_id"], data["last_move"]["id"])
        self.assertIn("version", data)
        self.assertEqual(response.headers["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0")

    @patch("games.views.broadcast_move_created")
    def test_http_save_move_broadcasts_to_game_group_after_save(self, broadcast_move_created):
        white, _black, game = self.create_multiplayer_game()

        response = self.post_move(white, game, "e2", "e4")

        self.assertEqual(response.status_code, 200)
        broadcast_move_created.assert_called_once()
        game_id, actor, result, guest_id = broadcast_move_created.call_args.args
        self.assertEqual(game_id, game.id)
        self.assertEqual(actor, white)
        self.assertIsNone(guest_id)
        self.assertEqual(result["move_id"], game.moves.get().id)
        self.assertEqual(result["state"]["move_count"], 1)

    def test_legacy_moves_endpoint_still_returns_latest_moves(self):
        white, black, game = self.create_multiplayer_game()
        self.assertEqual(self.post_move(white, game, "e2", "e4").status_code, 200)

        self.client.force_login(black)
        response = self.client.get(reverse("game_moves", args=[game.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["moves"][0]["to"], "e4")

    def test_save_move_requires_csrf_when_checks_are_enforced(self):
        white, _black, game = self.create_multiplayer_game()
        client = Client(enforce_csrf_checks=True)
        client.force_login(white)

        response = client.post(
            reverse("save_move", args=[game.id]),
            data=json.dumps({"from": "e2", "to": "e4"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_too_many_engine_moves_is_rejected_before_stockfish(self):
        user = User.objects.create_user(username="engine-abuse", password="pass")
        self.client.force_login(user)

        response = self.client.post(
            reverse("engine_move"),
            data=json.dumps({"moves": [{}] * 301, "elo": 1320}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_rate_limit_returns_retry_after_header(self):
        cache.clear()
        user = User.objects.create_user(username="engine-rate-limit", password="pass")
        self.client.force_login(user)

        payload = json.dumps({"moves": [{}] * 301, "elo": 1320})

        try:
            for _index in range(30):
                response = self.client.post(
                    reverse("engine_move"),
                    data=payload,
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)

            response = self.client.post(
                reverse("engine_move"),
                data=payload,
                content_type="application/json",
            )
        finally:
            cache.clear()

        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)

    def test_anonymous_rate_limit_uses_browser_session_before_proxy_ip(self):
        cache.clear()
        payload = json.dumps({"moves": [{}] * 301, "elo": 1320})
        first_client = Client(REMOTE_ADDR="10.0.0.8", HTTP_HOST="localhost")
        second_client = Client(REMOTE_ADDR="10.0.0.8", HTTP_HOST="localhost")
        first_session = first_client.session
        first_session["rate_limit_id"] = "browser-token-one"
        first_session.save()
        second_session = second_client.session
        second_session["rate_limit_id"] = "browser-token-two"
        second_session.save()

        def post_bad_engine_move(client):
            return client.post(
                reverse("engine_move"),
                data=payload,
                content_type="application/json",
            )

        try:
            for _index in range(30):
                self.assertEqual(post_bad_engine_move(first_client).status_code, 400)

            self.assertEqual(post_bad_engine_move(first_client).status_code, 429)
            self.assertEqual(post_bad_engine_move(second_client).status_code, 400)
        finally:
            cache.clear()

    def test_invalid_pgn_does_not_break_analyzer(self):
        user = User.objects.create_user(username="player", password="pass")

        self.client.force_login(user)
        response = self.client.post(reverse("game_analyzer"), data={"pgn": "this is not pgn"})

        self.assertEqual(response.status_code, 200)

    def test_pgn_analyzer_form_includes_cancelable_loading_overlay(self):
        response = self.client.get(reverse("game_analyzer"))

        self.assertContains(response, 'id="pgn-analysis-form"')
        self.assertContains(response, 'id="analysis-loading-overlay"')
        self.assertContains(response, 'id="cancel-analysis-loading"')
        self.assertContains(response, 'games/analysis_loading.js')
        self.assertContains(response, "GChessAnalysisLoading.bindForm('pgn-analysis-form')")

    def test_home_analyze_button_uses_full_navigation_loading_overlay(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'id="analysis-loading-overlay"')
        self.assertContains(response, 'id="cancel-analysis-loading"')
        self.assertContains(response, 'games/analysis_loading.js')
        self.assertContains(response, "GChessAnalysisLoading.bindForm('analyze-game-form', { navigate: true })")

    def test_analyzer_page_uses_computer_coach_chat_structure(self):
        template = open("games/templates/games/game_analyzer.html", encoding="utf-8").read()

        self.assertIn('computer-play-panel', template)
        self.assertIn('analyzer-game-layout', template)
        self.assertIn('analyzer-side', template)
        self.assertIn('id="computer-coach-panel"', template)
        self.assertIn('id="trainer-chat-form"', template)
        self.assertIn('id="analysis-comment"', template)
        self.assertIn('id="leave-analysis-modal"', template)
        self.assertIn('{% tr "first_position" %}', template)
        self.assertIn('games/analyzer_chat.js', template)
        self.assertIn("let PLAYER_COLOR = 'white';", template)

    def test_board_notifies_analyzer_when_position_changes(self):
        source = open("games/static/games/board.js", encoding="utf-8").read()
        analyzer = open("games/static/games/analyzer.js", encoding="utf-8").read()

        self.assertIn("gchess:position-changed", source)
        self.assertIn("gchessHistoryIndex", source)
        self.assertIn("gchess:position-changed", analyzer)
        self.assertIn("ANALYZER_MODE", source)
        self.assertIn("loadPositionUntil(0)", source)

    def test_board_websocket_reconnects_with_backoff_and_state_sync(self):
        source = open("games/static/games/board.js", encoding="utf-8").read()

        self.assertIn("GAME_SOCKET_RECONNECT_BASE_MS", source)
        self.assertIn("GAME_SOCKET_RECONNECT_MAX_MS", source)
        self.assertIn("nextGameSocketReconnectDelay", source)
        self.assertIn("socketLog('close'", source)
        self.assertIn("socketLog('reconnect scheduled'", source)
        self.assertIn("socketLog('received'", source)
        self.assertIn("syncMovesFromServer({ source: wasReconnect ? 'websocket-reconnect' : 'websocket-open' })", source)

    def test_bot_finished_status_uses_board_toolbar_and_dims_coach_panel(self):
        home = open("games/templates/games/home.html", encoding="utf-8").read()
        board_source = open("games/static/games/board.js", encoding="utf-8").read()
        styles = open("games/static/games/style.css", encoding="utf-8").read()

        toolbar_start = home.index('<div class="board-toolbar">')
        toolbar_end = home.index('<div id="board" class="board"></div>')
        pgn_start = home.index('id="computer-pgn-panel"')
        pgn_end = home.index('<ul id="move-list"', pgn_start)

        self.assertIn('id="game-status"', home[toolbar_start:toolbar_end])
        self.assertNotIn('id="game-status"', home[pgn_start:pgn_end])
        self.assertIn("const computerCoachPanel = document.getElementById('computer-coach-panel')", board_source)
        self.assertIn("computerCoachPanel.classList.toggle('game-finished-panel', gameOver)", board_source)
        self.assertIn(".computer-panel.game-finished-panel > :not(.computer-controls)", styles)

    def test_bot_requests_have_duplicate_and_rate_limit_guards(self):
        source = open("games/static/games/board.js", encoding="utf-8").read()

        self.assertIn("let isEngineThinking = false", source)
        self.assertIn("let isCoachAnalysisLoading = false", source)
        self.assertIn("COACH_ANALYSIS_DEBOUNCE_MS", source)
        self.assertIn("coachAnalysisCooldownUntil", source)
        self.assertIn("scheduleCoachAnalysis()", source)
        self.assertIn("retryDelayFromResponse(response", source)
        self.assertIn("scheduleEngineMoveRetry(requestKey, elo, engineMoveRetryDelay(response))", source)
        self.assertIn("response.status === 429", source)
        self.assertIn("neutralCoachFallbackComment()", source)
        self.assertIn("resetBotLoadingState()", source)
        self.assertIn("engineMoveAbortController.abort()", source)
        self.assertIn("coachAnalysisAbortController.abort()", source)

    def test_analysis_comments_are_short_and_do_not_overpunish_small_loss(self):
        comment = generate_comment(40, "mover el caballo a f3", "desarrollar el alfil a c4", "es")

        self.assertIn("Buena jugada", comment)
        self.assertIn("mover el caballo a f3", comment)
        self.assertNotIn("Imprecision", comment)
        self.assertLess(len(comment), 140)

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


class GameCreationTests(TestCase):
    def test_anonymous_user_can_create_casual_link_invitation(self):
        response = self.client.post(reverse("game_create"), data={
            "game_type": "casual",
            "opponent_mode": "link",
            "color_choice": "white",
            "time_control_minutes": "",
        })

        invitation = GameInvitation.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(invitation.creator)
        self.assertFalse(invitation.is_rated)
        self.assertEqual(invitation.opponent_mode, "link")
        self.assertTrue(invitation.creator_guest_id)
        self.assertTrue(invitation.creator_guest_name.startswith("Invitado"))

    def test_anonymous_user_cannot_force_ranked_invitation(self):
        response = self.client.post(reverse("game_create"), data={
            "game_type": "ranked",
            "opponent_mode": "link",
            "color_choice": "white",
            "time_control_minutes": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(GameInvitation.objects.count(), 0)

    def test_guest_link_players_can_open_state_and_move(self):
        creator_client = Client()
        opponent_client = Client()

        creator_client.post(reverse("game_create"), data={
            "game_type": "casual",
            "opponent_mode": "link",
            "color_choice": "white",
            "time_control_minutes": "",
        })
        invitation = GameInvitation.objects.get()

        accept_response = opponent_client.get(reverse("accept_invitation_link", args=[invitation.token]))
        invitation.refresh_from_db()
        game = invitation.game

        self.assertRedirects(accept_response, reverse("game_detail", args=[game.id]))
        self.assertEqual(game.white_guest_id, invitation.creator_guest_id)
        self.assertEqual(game.black_guest_id, opponent_client.session["guest_id"])
        self.assertFalse(game.is_rated)

        move_response = creator_client.post(
            reverse("save_move", args=[game.id]),
            data=json.dumps({
                "from": "e2",
                "to": "e4",
                "piece_color": "white",
                "piece_type": "pawn",
            }),
            content_type="application/json",
        )
        state_response = opponent_client.get(reverse("game_state", args=[game.id]))

        self.assertEqual(move_response.status_code, 200)
        self.assertEqual(state_response.status_code, 200)
        self.assertEqual(state_response.json()["move_count"], 1)
        self.assertEqual(state_response.json()["turn"], "black")

    def test_logged_in_user_can_create_link_invitation(self):
        user = User.objects.create_user(username="creator", password="pass")
        self.client.force_login(user)

        response = self.client.post(reverse("game_create"), data={
            "opponent_mode": "link",
            "color_choice": "white",
            "time_control_minutes": "",
        })

        invitation = GameInvitation.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invitation.creator, user)
        self.assertEqual(invitation.opponent_mode, "link")
        self.assertEqual(invitation.status, "pending")

    def test_link_invitation_assigns_white_and_black_players(self):
        creator = User.objects.create_user(username="creator", password="pass")
        opponent = User.objects.create_user(username="opponent", password="pass")
        invitation = GameInvitation.objects.create(
            creator=creator,
            opponent_mode="link",
            creator_color="black",
        )

        self.client.force_login(opponent)
        self.client.get(reverse("accept_invitation_link", args=[invitation.token]))

        game = ChessGame.objects.get()
        self.assertEqual(game.white_user, opponent)
        self.assertEqual(game.black_user, creator)
        self.assertEqual(game.owner, creator)

    def test_invalid_invitation_link_returns_not_found(self):
        user = User.objects.create_user(username="link-user", password="pass")
        self.client.force_login(user)

        response = self.client.get(reverse("accept_invitation_link", args=["00000000-0000-0000-0000-000000000000"]))

        self.assertEqual(response.status_code, 404)


class StockfishEndpointTests(TestCase):
    class FakeEngine:
        options = {}

        def play(self, board, limit):
            return type("PlayResult", (), {"move": chess.Move.from_uci("e2e4")})()

        def quit(self):
            pass

    def test_engine_move_works_when_stockfish_path_exists(self):
        user = User.objects.create_user(username="engine-ok", password="pass")
        self.client.force_login(user)

        with patch.dict(os.environ, {"STOCKFISH_PATH": "/usr/games/stockfish"}), \
                patch("games.views.Path.exists", return_value=True), \
                patch("games.views.chess.engine.SimpleEngine.popen_uci", return_value=self.FakeEngine()):
            response = self.client.post(
                reverse("engine_move"),
                data=json.dumps({"moves": [], "elo": 1320}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["from"], "e2")
        self.assertEqual(response.json()["to"], "e4")

    def test_engine_move_accepts_different_supported_elos(self):
        user = User.objects.create_user(username="engine-elotest", password="pass")
        self.client.force_login(user)

        with patch.dict(os.environ, {"STOCKFISH_PATH": "/usr/games/stockfish"}), \
                patch("games.views.Path.exists", return_value=True), \
                patch("games.views.chess.engine.SimpleEngine.popen_uci", return_value=self.FakeEngine()):
            response = self.client.post(
                reverse("engine_move"),
                data=json.dumps({"moves": [], "elo": 2000}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)

    def test_trainer_chat_handles_languages_without_breaking(self):
        user = User.objects.create_user(username="trainer-user", password="pass")
        self.client.force_login(user)

        with patch("games.views.configured_stockfish_path", return_value=("stockfish", "")), \
                patch("games.views.chess.engine.SimpleEngine.popen_uci", return_value=self.FakeEngine()), \
                patch("games.views.build_trainer_chat_answer", return_value="ok"):
            for language in ("pt", "es", "en"):
                response = self.client.post(
                    reverse("trainer_chat"),
                    data=json.dumps({
                        "moves": [],
                        "question": "best move?",
                        "player_color": "white",
                        "language": language,
                    }),
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["answer"], "ok")

    def test_bot_game_automatic_comment_uses_stockfish_best_move(self):
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        after = board.copy()
        after.push(move)
        engine = FakeAnalysisEngine({
            board.fen(): fake_engine_analysis(20, [move]),
            after.fen(): fake_engine_analysis(25),
        })

        with patch("games.views.configured_stockfish_path", return_value=("stockfish", "")), \
                patch("games.views.open_stockfish_engine", return_value=engine):
            response = self.client.post(
                reverse("coach_analysis"),
                data=json.dumps({
                    "moves": [{"from": "e2", "to": "e4"}],
                    "player_color": "white",
                    "language": "en",
                }),
                content_type="application/json",
            )

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["classification"], "best")
        self.assertEqual(data["loss"], 0)
        self.assertNotIn("Inaccuracy", data["comment"])
        self.assertEqual(data["engine_context"]["played_move_uci"], "e2e4")
        self.assertEqual(data["engine_context"]["best_move_uci"], "e2e4")

    def test_pgn_analysis_automatic_comments_use_stockfish_classification(self):
        board = chess.Board()
        move = chess.Move.from_uci("e2e4")
        after = board.copy()
        after.push(move)
        engine = FakeAnalysisEngine({
            board.fen(): fake_engine_analysis(20, [move]),
            after.fen(): fake_engine_analysis(25),
        })

        with patch("games.views.configured_stockfish_path", return_value=("stockfish", "")), \
                patch("games.views.open_stockfish_engine", return_value=engine):
            response = self.client.post(
                reverse("game_analyzer"),
                data={"pgn": "1. e4"},
            )

        analysis = response.context["analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis[0]["classification"], "best")
        self.assertEqual(analysis[0]["loss"], 0)
        self.assertNotIn("Inaccuracy", analysis[0]["comment"])
        self.assertEqual(analysis[0]["engine_context"]["played_move_uci"], "e2e4")
        self.assertEqual(analysis[0]["engine_context"]["best_move_uci"], "e2e4")


class DeployReadinessTests(SimpleTestCase):
    def test_sensitive_local_files_are_ignored(self):
        gitignore = open(".gitignore", encoding="utf-8").read()

        self.assertIn(".env", gitignore)
        self.assertIn("db.sqlite3", gitignore)
        self.assertIn("staticfiles/", gitignore)

    def test_production_settings_are_environment_driven(self):
        settings_source = open("config/settings.py", encoding="utf-8").read()

        self.assertIn("os.environ.get('DJANGO_SECRET_KEY')", settings_source)
        self.assertIn("env_bool('DJANGO_DEBUG'", settings_source)
        self.assertIn("env_list('DJANGO_ALLOWED_HOSTS'", settings_source)
        self.assertIn("env_list('DJANGO_CSRF_TRUSTED_ORIGINS'", settings_source)

    def test_render_files_are_configured(self):
        build = open("build.sh", encoding="utf-8").read()
        dockerfile = open("Dockerfile", encoding="utf-8").read()
        procfile = open("Procfile", encoding="utf-8").read()
        requirements = open("requirements.txt", encoding="utf-8").read()

        self.assertIn("apt-get install -y stockfish", build)
        self.assertIn("collectstatic --no-input", build)
        self.assertIn("python manage.py migrate", build)
        self.assertIn("daphne", dockerfile)
        self.assertIn("config.asgi:application", dockerfile)
        self.assertNotIn("gunicorn config.wsgi:application", dockerfile)
        self.assertIn("daphne", procfile)
        self.assertIn("config.asgi:application", procfile)
        self.assertIn("channels", requirements)
        self.assertIn("daphne", requirements)
        self.assertIn("gunicorn", requirements)
        self.assertIn("whitenoise", requirements)

    def test_no_windows_stockfish_path_is_hardcoded_in_runtime_code(self):
        for path in ("games/views.py", "config/settings.py", "build.sh", "Procfile"):
            source = open(path, encoding="utf-8").read()
            self.assertNotIn(r"C:\Users\lucas", source)


class DailyVisitMiddlewareTests(TestCase):
    def test_counts_public_get_requests_by_day(self):
        self.client.get(reverse("home"))
        self.client.get(reverse("home"))

        daily_visit = DailyVisit.objects.get()
        self.assertEqual(daily_visit.visits, 2)

    def test_does_not_count_admin_requests(self):
        admin_user = User.objects.create_superuser(username="admin", password="pass")
        self.client.force_login(admin_user)

        self.client.get(reverse("admin:index"))

        self.assertEqual(DailyVisit.objects.count(), 0)
