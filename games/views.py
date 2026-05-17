from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import ChessGame
from .forms import ChessGameForm
from django.contrib.auth.decorators import login_required
import json
import chess
import random
import re
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import ChessGame, GameInvitation, Move, UserPresence

PROMOTION_PIECES = {
    'queen': 'q',
    'rook': 'r',
    'bishop': 'b',
    'horse': 'n',
}

ONLINE_SECONDS = 60


def online_since():
    return timezone.now() - timezone.timedelta(seconds=ONLINE_SECONDS)


def touch_presence(user):
    if user.is_authenticated:
        UserPresence.objects.update_or_create(user=user)


def game_access_filter(user):
    return Q(owner=user) | Q(white_user=user) | Q(black_user=user)


def get_game_for_user(game_id, user):
    return get_object_or_404(
        ChessGame,
        game_access_filter(user),
        id=game_id,
    )


def player_color_for_game(game, user):
    if game.white_user_id == user.id:
        return 'white'

    if game.black_user_id == user.id:
        return 'black'

    return None


def resolve_creator_color(color_choice):
    if color_choice == 'random':
        return random.choice(['white', 'black'])

    return color_choice


def create_game_from_invitation(invitation, opponent):
    creator_color = resolve_creator_color(invitation.creator_color)

    if creator_color == 'white':
        white_user = invitation.creator
        black_user = opponent
    else:
        white_user = opponent
        black_user = invitation.creator

    return ChessGame.objects.create(
        owner=invitation.creator,
        white_user=white_user,
        black_user=black_user,
        white_player=white_user.username,
        black_player=black_user.username,
    )

LOW_ELO_SKILL_LEVELS = {
    500: 0,
    800: 2,
    1000: 4,
}

LOW_ELO_WEAKNESS = {
    500: {
        "random_chance": 0.55,
        "candidate_count": 8,
        "weights": [8, 7, 6, 5, 4, 3, 2, 1],
        "time": 0.04,
    },
    800: {
        "random_chance": 0.32,
        "candidate_count": 6,
        "weights": [8, 6, 4, 3, 2, 1],
        "time": 0.06,
    },
    1000: {
        "random_chance": 0.18,
        "candidate_count": 4,
        "weights": [8, 5, 3, 1],
        "time": 0.08,
    },
}

def home(request):
    touch_presence(request.user)
    return render(request, 'games/home.html')


@login_required
def games_list(request):
    touch_presence(request.user)
    games = ChessGame.objects.filter(
        game_access_filter(request.user)
    ).prefetch_related('moves').order_by('-created_at')

    game_cards = []

    for game in games:
        finished_info = get_finished_game_info(game)
        sync_finished_game_status(game, finished_info)

        game_cards.append({
            'game': game,
            'status': build_game_list_status(game, request.user, finished_info),
            'is_finished': finished_info['finished'],
            'is_in_progress': not finished_info['finished'],
        })

    return render(request, 'games/games_list.html', {
        'game_cards': game_cards
    })


def build_game_list_status(game, user, finished_info):
    if finished_info['finished']:
        if game.result == 'draw':
            return {
                'text': 'Partida empatada',
                'class': 'game-card-status-draw',
            }

        user_color = get_user_color_for_game(game, user)
        winner = finished_info['winner'] or game.result

        if user_color and winner in ('white', 'black'):
            return {
                'text': 'Partida vencida' if winner == user_color else 'Partida perdida',
                'class': 'game-card-status-won' if winner == user_color else 'game-card-status-lost',
            }

        return {
            'text': 'Partida finalizada',
            'class': 'game-card-status-finished',
        }

    moves_count = game.moves.count()
    next_turn = 'brancas' if moves_count % 2 == 0 else 'pretas'

    return {
        'text': f'Vez das {next_turn}',
        'class': 'game-card-status-turn',
    }


def get_finished_game_info(game):
    if game.status == 'finished':
        return {
            'finished': True,
            'winner': game.result if game.result in ('white', 'black') else None,
        }

    board = chess.Board()

    for move in game.moves.all().order_by('move_number', 'id'):
        try:
            chess_move = build_chess_move(move)
        except ValueError:
            return {'finished': False, 'winner': None}

        if chess_move not in board.legal_moves:
            return {'finished': False, 'winner': None}

        board.push(chess_move)

    if board.is_checkmate():
        winner = 'black' if board.turn == chess.WHITE else 'white'
        return {'finished': True, 'winner': winner}

    return {'finished': False, 'winner': None}


def build_chess_move(move):
    promotion = PROMOTION_PIECES.get(move.promotion or '')
    return chess.Move.from_uci(f'{move.from_square}{move.to_square}{promotion or ""}')


def sync_finished_game_status(game, finished_info):
    if not finished_info['finished'] or game.status == 'finished':
        return

    game.status = 'finished'

    if finished_info['winner'] in ('white', 'black'):
        game.result = finished_info['winner']

    game.save(update_fields=['status', 'result'])


def get_user_color_for_game(game, user):
    if not user.is_authenticated:
        return None

    user_names = {
        value.strip().casefold()
        for value in (
            user.get_full_name(),
            user.get_username(),
            getattr(user, 'email', ''),
        )
        if value and value.strip()
    }

    if game.white_player.strip().casefold() in user_names:
        return 'white'

    if game.black_player.strip().casefold() in user_names:
        return 'black'

    return None

@login_required
def game_detail(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)
    player_color = player_color_for_game(game, request.user)
    moves = [
        {
            'move_number': move.move_number,
            'from': move.from_square,
            'to': move.to_square,
            'piece_type': move.piece_type,
            'piece_color': move.piece_color,
            'promotion': move.promotion,
        }
        for move in game.moves.all().order_by('move_number')
    ]

    return render(request, 'games/game_detail.html', {
        'game': game,
        'moves': moves,
        'player_color': player_color,
        'multiplayer_mode': bool(game.white_user_id and game.black_user_id),
    })

@login_required   
def game_create(request):
    touch_presence(request.user)
    if request.method == 'POST':
        form = ChessGameForm(request.POST)

        if form.is_valid():
            opponent_mode = form.cleaned_data['opponent_mode']
            opponent = form.get_opponent_user()

            if opponent_mode == 'choose':
                if not opponent:
                    form.add_error('opponent_name', 'Esse usuário não está online ou não existe.')
                elif opponent == request.user:
                    form.add_error('opponent_name', 'Você não pode jogar contra você mesmo.')
                else:
                    invitation = GameInvitation.objects.create(
                        creator=request.user,
                        opponent=opponent,
                        opponent_mode='direct',
                        creator_color=form.cleaned_data['color_choice'],
                    )
                    return redirect('game_invitation_wait', invitation_id=invitation.id)
            else:
                invitation = GameInvitation.objects.create(
                    creator=request.user,
                    opponent_mode='random',
                    creator_color=form.cleaned_data['color_choice'],
                )
                return redirect('game_invitation_wait', invitation_id=invitation.id)
    else:
        form = ChessGameForm()

    return render(request, 'games/game_create.html', {
        'form': form
    })
    
@login_required
@require_POST
def save_move(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)
    data = json.loads(request.body)
    player_color = player_color_for_game(game, request.user)
    expected_color = 'white' if game.moves.count() % 2 == 0 else 'black'

    if player_color and data.get('piece_color') != player_color:
        return JsonResponse({'error': 'Você só pode mover suas próprias peças.'}, status=403)

    if data.get('piece_color') != expected_color:
        return JsonResponse({'error': 'Não é a vez dessa cor.'}, status=400)

    move = Move.objects.create(
        game=game,
        move_number=data['move_number'],
        from_square=data['from'],
        to_square=data['to'],
        piece_type=data['piece_type'],
        piece_color=data['piece_color'],
        promotion=data.get('promotion'),
    )

    if data.get('game_finished'):
        game.status = 'finished'

        if data.get('winner') in ('white', 'black'):
            game.result = data['winner']

        game.save(update_fields=['status', 'result'])

    return JsonResponse({
        'status': 'ok',
        'move_id': move.id
    })


@login_required
@require_POST
def mark_finished(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)

    data = json.loads(request.body)

    game.status = 'finished'

    if data.get('winner') in ('white', 'black'):
        game.result = data['winner']

    game.save(update_fields=['status', 'result'])

    return JsonResponse({
        'status': 'ok',
    })


@login_required
def game_invitation_wait(request, invitation_id):
    touch_presence(request.user)
    invitation = get_object_or_404(GameInvitation, id=invitation_id, creator=request.user)

    return render(request, 'games/game_invitation_wait.html', {
        'invitation': invitation,
    })


@login_required
def invitation_status(request, invitation_id):
    touch_presence(request.user)
    invitation = get_object_or_404(GameInvitation, id=invitation_id, creator=request.user)

    return JsonResponse({
        'status': invitation.status,
        'game_id': invitation.game_id,
        'game_url': f'/partidas/{invitation.game_id}/' if invitation.game_id else None,
    })


@login_required
@require_POST
def cancel_invitation(request, invitation_id):
    touch_presence(request.user)
    invitation = get_object_or_404(GameInvitation, id=invitation_id, creator=request.user)

    updated_count = GameInvitation.objects.filter(
        id=invitation.id,
        status='pending',
    ).update(
        status='cancelled',
        responded_at=timezone.now(),
    )

    if updated_count == 0:
        return JsonResponse({'error': 'Esse convite não pode mais ser cancelado.'}, status=409)

    return JsonResponse({
        'status': 'cancelled',
        'redirect_url': '/partidas/',
    })


@login_required
def game_notifications(request):
    touch_presence(request.user)
    invitations = GameInvitation.objects.filter(
        status='pending',
    ).filter(
        Q(opponent=request.user) |
        Q(opponent_mode='random', opponent__isnull=True)
    ).exclude(
        creator=request.user
    ).select_related('creator').order_by('created_at')[:8]

    return JsonResponse({
        'invitations': [
            {
                'id': invitation.id,
                'creator': invitation.creator.username,
                'opponent_mode': invitation.opponent_mode,
                'creator_color': invitation.creator_color,
            }
            for invitation in invitations
        ]
    })


@login_required
@require_POST
def accept_invitation(request, invitation_id):
    touch_presence(request.user)

    with transaction.atomic():
        invitation = get_object_or_404(GameInvitation, id=invitation_id)

        if invitation.creator_id == request.user.id:
            return JsonResponse({'error': 'Você não pode aceitar seu próprio convite.'}, status=403)

        if invitation.status != 'pending':
            return JsonResponse({'error': 'Esse convite não está mais disponível.'}, status=409)

        if invitation.opponent_id and invitation.opponent_id != request.user.id:
            return JsonResponse({'error': 'Esse convite é para outro jogador.'}, status=403)

        accepted_count = GameInvitation.objects.filter(
            id=invitation_id,
            status='pending',
        ).filter(
            Q(opponent=request.user) |
            Q(opponent_mode='random', opponent__isnull=True)
        ).exclude(
            creator=request.user
        ).update(
            opponent=request.user,
            status='accepted',
            responded_at=timezone.now(),
        )

        if accepted_count == 0:
            return JsonResponse({'error': 'Esse convite não está mais disponível.'}, status=409)

        invitation = GameInvitation.objects.select_related('creator', 'opponent').get(id=invitation_id)
        game = create_game_from_invitation(invitation, request.user)
        invitation.game = game
        invitation.save(update_fields=['game'])

    return JsonResponse({
        'status': 'accepted',
        'game_id': game.id,
        'game_url': f'/partidas/{game.id}/',
    })


@login_required
@require_POST
def reject_invitation(request, invitation_id):
    touch_presence(request.user)
    invitation = get_object_or_404(GameInvitation, id=invitation_id, status='pending')

    if invitation.opponent_id and invitation.opponent_id != request.user.id:
        return JsonResponse({'error': 'Esse convite é para outro jogador.'}, status=403)

    if invitation.creator_id == request.user.id:
        return JsonResponse({'error': 'Você não pode recusar seu próprio convite.'}, status=403)

    if invitation.opponent_mode == 'direct':
        invitation.status = 'rejected'
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=['status', 'responded_at'])

    return JsonResponse({'status': 'rejected'})


@login_required
def game_moves(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)

    moves = [
        {
            'move_number': move.move_number,
            'from': move.from_square,
            'to': move.to_square,
            'piece_type': move.piece_type,
            'piece_color': move.piece_color,
            'promotion': move.promotion,
        }
        for move in game.moves.all().order_by('move_number')
    ]

    return JsonResponse({'moves': moves})

import chess.pgn
import chess.engine
from io import StringIO
from pathlib import Path

STOCKFISH_PATH = r"C:\Users\lucas\Downloads\stockfish-windows-x86-64-avx2\stockfish\stockfish-windows-x86-64-avx2.exe"
ANALYSIS_LIMIT = chess.engine.Limit(time=0.05)
INTERNAL_MOVE_PATTERN = re.compile(
    r"^\s*(?:\d+\.\s*)?([a-h][1-8])\s*->\s*([a-h][1-8])"
    r"(?:\s*(?:=|\()?\s*(queen|rook|bishop|horse|knight|dama|torre|bispo|cavalo|[qrbn])\)?)?\s*$",
    re.IGNORECASE,
)
INTERNAL_PROMOTIONS = {
    "queen": chess.QUEEN,
    "dama": chess.QUEEN,
    "q": chess.QUEEN,
    "rook": chess.ROOK,
    "torre": chess.ROOK,
    "r": chess.ROOK,
    "bishop": chess.BISHOP,
    "bispo": chess.BISHOP,
    "b": chess.BISHOP,
    "horse": chess.KNIGHT,
    "knight": chess.KNIGHT,
    "cavalo": chess.KNIGHT,
    "n": chess.KNIGHT,
}

@require_POST
def engine_move(request):
    data = json.loads(request.body)

    moves = data.get("moves", [])
    elo = int(data.get("elo", 1200))

    board = chess.Board()

    for move_data in moves:
        promotion = PROMOTION_PIECES.get(move_data.get("promotion") or "")
        uci = f"{move_data['from']}{move_data['to']}{promotion or ''}"
        move = chess.Move.from_uci(uci)

        if move in board.legal_moves:
            board.push(move)

    if board.is_game_over():
        return JsonResponse({
            "error": "A partida já terminou.",
        }, status=400)

    if not Path(STOCKFISH_PATH).exists():
        return JsonResponse({
            "error": "Não encontrei o Stockfish na rota configurada.",
        }, status=500)

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

    try:
        skill_level = LOW_ELO_SKILL_LEVELS.get(elo)

        if skill_level is not None and "Skill Level" in engine.options:
            engine.configure({
                "Skill Level": skill_level,
            })
        elif "UCI_LimitStrength" in engine.options and "UCI_Elo" in engine.options:
            elo_option = engine.options["UCI_Elo"]
            min_elo = elo_option.min or elo
            max_elo = elo_option.max or elo
            supported_elo = max(min_elo, min(max_elo, elo))

            engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": supported_elo,
            })

        move = choose_engine_move(engine, board, elo)

        piece = board.piece_at(move.from_square)

        response = {
            "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square),
            "piece_type": {
                chess.PAWN: "pawn",
                chess.KNIGHT: "horse",
                chess.BISHOP: "bishop",
                chess.ROOK: "rook",
                chess.QUEEN: "queen",
                chess.KING: "king",
            }[piece.piece_type],
            "piece_color": "white" if piece.color == chess.WHITE else "black",
            "promotion": {
                chess.QUEEN: "queen",
                chess.ROOK: "rook",
                chess.BISHOP: "bishop",
                chess.KNIGHT: "horse",
            }.get(move.promotion),
        }

        return JsonResponse(response)
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError) as exc:
        return JsonResponse({
            "error": f"Não foi possível calcular a jogada: {exc}",
        }, status=500)

    finally:
        engine.quit()


def choose_engine_move(engine, board, elo):
    weakness = LOW_ELO_WEAKNESS.get(elo)

    if not weakness:
        return engine.play(board, chess.engine.Limit(time=0.3)).move

    legal_moves = list(board.legal_moves)

    if random.random() < weakness["random_chance"]:
        return random.choice(legal_moves)

    candidate_count = min(weakness["candidate_count"], len(legal_moves))
    analyses = engine.analyse(
        board,
        chess.engine.Limit(time=weakness["time"]),
        multipv=candidate_count,
    )

    candidates = [
        analysis["pv"][0]
        for analysis in analyses
        if analysis.get("pv")
    ]

    if not candidates:
        return random.choice(legal_moves)

    weights = weakness["weights"][:len(candidates)]

    return random.choices(candidates, weights=weights, k=1)[0]


@require_POST
def coach_analysis(request):
    data = json.loads(request.body)
    moves = data.get("moves", [])
    player_color = data.get("player_color", "white")

    if not moves:
        return JsonResponse({
            "error": "Não há jogadas para analisar.",
        }, status=400)

    if not Path(STOCKFISH_PATH).exists():
        return JsonResponse({
            "error": "Não encontrei o Stockfish na rota configurada.",
        }, status=500)

    board = chess.Board()

    try:
        for move_data in moves[:-1]:
            move = build_move_from_data(move_data)

            if move not in board.legal_moves:
                return JsonResponse({
                    "error": "A partida contém uma jogada ilegal.",
                }, status=400)

            board.push(move)

        played_move = build_move_from_data(moves[-1])

        if played_move not in board.legal_moves:
            return JsonResponse({
                "error": "A última jogada não é legal.",
            }, status=400)
    except (KeyError, ValueError):
        return JsonResponse({
            "error": "Não consegui ler as jogadas para analisá-las.",
        }, status=400)

    moving_piece = board.piece_at(played_move.from_square)
    moving_color = "white" if moving_piece and moving_piece.color == chess.WHITE else "black"

    if moving_color != player_color:
        return JsonResponse({
            "comment": "",
        })

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

    try:
        before = engine.analyse(board, ANALYSIS_LIMIT)
        before_score = score_to_cp(before["score"].white())
        best_move = before.get("pv", [played_move])[0]
        played_san = board.san(played_move)
        best_san = board.san(best_move)

        context_board = board.copy()
        board.push(played_move)

        after = engine.analyse(board, ANALYSIS_LIMIT)
        after_score = score_to_cp(after["score"].white())

        loss = before_score - after_score if moving_color == "white" else after_score - before_score
        loss = max(0, loss)

        return JsonResponse({
            "comment": coach_comment(
                loss,
                context_board,
                played_move,
                best_move,
                played_san,
                best_san,
                before_score,
                after_score,
            ),
            "loss": loss,
            "played": played_san,
            "best": best_san,
        })
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError) as exc:
        return JsonResponse({
            "error": f"Não foi possível analisar a jogada: {exc}",
        }, status=500)
    finally:
        engine.quit()


def build_move_from_data(move_data):
    promotion = PROMOTION_PIECES.get(move_data.get("promotion") or "")
    return chess.Move.from_uci(f"{move_data['from']}{move_data['to']}{promotion or ''}")


def board_from_move_data(moves):
    board = chess.Board()
    san_moves = []

    for move_data in moves:
        move = build_move_from_data(move_data)

        if move not in board.legal_moves:
            raise ValueError("A partida contém uma jogada ilegal.")

        san_moves.append(board.san(move))
        board.push(move)

    return board, san_moves


@require_POST
def trainer_chat(request):
    data = json.loads(request.body)
    question = data.get("question", "").strip()
    moves = data.get("moves", [])
    player_color = data.get("player_color", "white")

    if not question:
        return JsonResponse({
            "answer": "Pergunte algo sobre a posição atual.",
        })

    try:
        board, san_moves = board_from_move_data(moves)
    except (KeyError, ValueError):
        return JsonResponse({
            "error": "Não consegui ler a posição atual.",
        }, status=400)

    if not Path(STOCKFISH_PATH).exists():
        return JsonResponse({
            "error": "Não encontrei o Stockfish na rota configurada.",
        }, status=500)

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

    try:
        answer = build_trainer_chat_answer(engine, board, san_moves, question, player_color)

        return JsonResponse({
            "answer": answer,
        })
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError) as exc:
        return JsonResponse({
            "error": f"Não foi possível responder agora: {exc}",
        }, status=500)
    finally:
        engine.quit()


def build_trainer_chat_answer(engine, board, san_moves, question, player_color):
    question_text = question.casefold()
    analysis = engine.analyse(board, chess.engine.Limit(time=0.12))
    best_move = analysis.get("pv", [None])[0]
    score = score_to_cp(analysis["score"].white())
    opening_name = detect_opening(san_moves)
    player_is_to_move = (board.turn == chess.WHITE and player_color == "white") or (board.turn == chess.BLACK and player_color == "black")

    if best_move is None:
        return "Não encontrei uma recomendação clara nesta posição."

    best_san = board.san(best_move)
    best_ideas = " ".join(describe_coach_ideas(board, best_move))
    evaluation = describe_position_for_player(score, player_color)

    if any(word in question_text for word in ("jogada", "jugada", "lance", "movimiento", "movimento", "última", "ultima", "essa", "esa")):
        last_move_answer = describe_last_move_for_chat(engine, board, san_moves)
        if last_move_answer:
            return last_move_answer

    if any(word in question_text for word in ("abertura", "nome", "linha")):
        return (
            f"A abertura parece ser: {opening_name}. "
            f"Pelo plano atual, olhe principalmente para o centro, desenvolvimento das peças e segurança do rei."
        )

    if any(word in question_text for word in ("recomenda", "recomend", "mover", "jogar", "faço", "fazer", "ajuda")):
        if player_is_to_move:
            return (
                f"Eu consideraria {best_san}. {best_ideas} "
                f"Antes de mover, confira quais peças suas ficam defendidas e que casas você passa a atacar."
            )

        return (
            "Agora é a vez do computador. Enquanto espera, observe a ameaça principal dele: "
            f"a melhor continuação indicada é {best_san}, então preste atenção nas casas e peças ligadas a essa jogada."
        )

    if any(word in question_text for word in ("ameaça", "ameaças", "ataca", "ataque", "defendo", "defender")):
        threats = describe_current_threats(board)
        return f"{threats} Também olhe se suas peças avançadas estão defendidas por outra peça."

    if any(word in question_text for word in ("melhor", "pior", "vantagem", "avalia", "ganhando", "perdendo")):
        return (
            f"{evaluation} A sugestão do motor é {best_san}. "
            f"O ponto importante é entender se você está ganhando atividade, material ou segurança do rei."
        )

    return (
        f"Minha leitura rápida: {evaluation} Uma ideia concreta é {best_san}. {best_ideas} "
        f"Olhe primeiro para centro, peças atacadas, peças sem defesa e segurança do rei."
    )


def describe_last_move_for_chat(engine, board, san_moves):
    if not board.move_stack:
        return "Ainda estamos na posição inicial; não há uma jogada anterior para comentar."

    previous_board = board.copy(stack=True)
    played_move = previous_board.pop()
    before = engine.analyse(previous_board, ANALYSIS_LIMIT)
    before_score = score_to_cp(before["score"].white())
    best_move = before.get("pv", [played_move])[0]
    played_san = previous_board.san(played_move)
    best_san = previous_board.san(best_move)
    after_score = score_to_cp(engine.analyse(board, ANALYSIS_LIMIT)["score"].white())
    moving_piece = previous_board.piece_at(played_move.from_square)

    if moving_piece and moving_piece.color == chess.WHITE:
        loss = before_score - after_score
    else:
        loss = after_score - before_score

    loss = max(0, loss)
    comment = coach_comment(
        loss,
        previous_board,
        played_move,
        best_move,
        played_san,
        best_san,
        before_score,
        after_score,
    )

    return f"Sobre a jogada {len(san_moves)}. {played_san}: {comment}"


def describe_position_for_player(score, player_color):
    perspective = score if player_color == "white" else -score

    if perspective > 180:
        return "Você está melhor, com vantagem clara."

    if perspective > 60:
        return "Você está um pouco melhor."

    if perspective < -180:
        return "Você está pior e precisa buscar atividade ou simplificar."

    if perspective < -60:
        return "Você está um pouco pior, então cuide das peças soltas e do rei."

    return "A posição está relativamente equilibrada."


def describe_current_threats(board):
    checks = []
    captures = []

    for move in board.legal_moves:
        if board.gives_check(move):
            checks.append(board.san(move))
        elif board.is_capture(move):
            piece = board.piece_at(move.to_square)
            if piece and piece.piece_type != chess.KING:
                captures.append(board.san(move))

    if checks:
        return f"Existem xeques candidatos para quem joga agora: {', '.join(checks[:3])}."

    if captures:
        return f"As capturas imediatas mais importantes para observar são: {', '.join(captures[:4])}."

    return "Não vejo uma captura ou xeque imediato muito óbvio; a briga principal parece ser por casas e desenvolvimento."


def coach_comment(loss, board, played_move, best_move, played_san, best_san, before_score, after_score):
    played_ideas = describe_coach_ideas(board, played_move)
    best_ideas = describe_coach_ideas(board, best_move)
    played_explanation = " ".join(played_ideas)
    best_explanation = " ".join(best_ideas)
    evaluation = describe_evaluation_change(board.turn, before_score, after_score)

    if loss < 30:
        return (
            f"Boa jogada: {played_san}. {played_explanation} "
            f"{evaluation} Continue olhando onde suas peças atacam e quais casas importantes elas defendem."
        )

    if loss < 80:
        return (
            f"Imprecisão: {played_san}. {played_explanation} "
            f"{evaluation} Eu consideraria {best_san}: {best_explanation}"
        )

    if loss < 180:
        return (
            f"Erro: {played_san} piora a posição. {played_explanation} "
            f"{evaluation} Melhor era {best_san}: {best_explanation}"
        )

    return (
        f"Lance muito ruim: {played_san} perde muita força na posição. {played_explanation} "
        f"{evaluation} A recomendação era {best_san}: {best_explanation}"
    )


def describe_coach_ideas(board, move):
    piece = board.piece_at(move.from_square)

    if piece is None:
        return ["A jogada não pôde ser descrita com precisão."]

    ideas = []
    piece_name = piece_name_pt(piece.piece_type)
    from_square = chess.square_name(move.from_square)
    to_square = chess.square_name(move.to_square)
    target_piece = board.piece_at(move.to_square)
    is_capture = board.is_capture(move)
    board_after = board.copy()
    board_after.push(move)

    if board.gives_check(move):
        ideas.append("Você cria uma ameaça direta ao rei com xeque.")

    if is_capture:
        captured_piece = target_piece

        if captured_piece is None and piece.piece_type == chess.PAWN:
            captured_piece = board.piece_at(chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square)))

        if captured_piece:
            ideas.append(f"É uma captura: seu {piece_name} ganha um {piece_name_pt(captured_piece.piece_type)}.")
        else:
            ideas.append("É uma captura tática.")
    elif piece.piece_type in (chess.KNIGHT, chess.BISHOP) and from_square in ("b1", "g1", "b8", "g8", "c1", "f1", "c8", "f8"):
        ideas.append(f"Você desenvolve o {piece_name}, tirando uma peça da casa inicial.")
    elif piece.piece_type == chess.PAWN and to_square[0] in ("d", "e"):
        ideas.append("Você disputa o centro, que é uma boa forma de ganhar espaço.")
    else:
        ideas.append(f"Você move o {piece_name} para {to_square}.")

    attacked_by_enemy = board_after.is_attacked_by(not piece.color, move.to_square)
    defended_by_friend = board_after.is_attacked_by(piece.color, move.to_square)

    if attacked_by_enemy and not defended_by_friend:
        ideas.append("Atenção: essa peça fica atacada e não parece bem defendida.")
    elif attacked_by_enemy and defended_by_friend:
        ideas.append("A peça fica em uma casa disputada: está atacada, mas também defendida.")
    elif defended_by_friend:
        ideas.append("A peça fica apoiada pelas suas outras peças.")

    attacked_targets = valuable_attacked_targets(board_after, piece.color, move.to_square)

    if attacked_targets:
        ideas.append(f"Além disso, ela passa a mirar {', '.join(attacked_targets)}.")

    return ideas


def valuable_attacked_targets(board, color, from_square):
    targets = []

    for square in board.attacks(from_square):
        piece = board.piece_at(square)

        if piece and piece.color != color and piece.piece_type != chess.KING:
            targets.append(f"{piece_name_pt(piece.piece_type)} em {chess.square_name(square)}")

    return targets[:2]


def describe_evaluation_change(turn, before_score, after_score):
    change = after_score - before_score if turn == chess.WHITE else before_score - after_score

    if abs(change) < 30:
        return "A avaliação quase não muda, então a posição continua equilibrada dentro do plano."

    if change > 0:
        return "A avaliação melhora para você, sinal de que a jogada aumenta sua pressão ou segurança."

    return "A avaliação cai para você, então algo na posição ficou mais vulnerável."


def piece_name_pt(piece_type):
    return {
        chess.PAWN: "peão",
        chess.KNIGHT: "cavalo",
        chess.BISHOP: "bispo",
        chess.ROOK: "torre",
        chess.QUEEN: "dama",
        chess.KING: "rei",
    }[piece_type]


def classify_move(loss):
    if loss is None:
        return "Jogada analisada."

    if loss < 30:
        return "Boa jogada."
    elif loss < 80:
        return "Imprecisão."
    elif loss < 180:
        return "Erro."
    else:
        return "Lance muito ruim."


def score_to_cp(score):
    if score.is_mate():
        mate = score.mate()
        return 100000 if mate > 0 else -100000

    return score.score(mate_score=100000) or 0

def detect_opening(san_moves):
    line = " ".join(san_moves[:6])

    if line.startswith("e4 e5 Nf3 Nc6 Bb5"):
        return "Ruy Lopez / Abertura Espanhola"

    if line.startswith("e4 c5"):
        return "Defesa Siciliana"

    if line.startswith("d4 d5 c4"):
        return "Gambito da Dama"

    if line.startswith("e4 e6"):
        return "Defesa Francesa"

    if line.startswith("e4 c6"):
        return "Defesa Caro-Kann"

    if line.startswith("d4 Nf6 c4 g6"):
        return "Defesa Índia do Rei"

    return "Abertura não identificada"

def describe_move(board, move):
    piece = board.piece_at(move.from_square)
    if piece is None:
        return board.san(move)

    piece_name = {
        chess.PAWN: "peão",
        chess.KNIGHT: "cavalo",
        chess.BISHOP: "bispo",
        chess.ROOK: "torre",
        chess.QUEEN: "dama",
        chess.KING: "rei",
    }[piece.piece_type]

    from_square = chess.square_name(move.from_square)
    to_square = chess.square_name(move.to_square)

    if board.is_capture(move):
        return f"capturar em {to_square} com o {piece_name} de {from_square}"

    return f"mover o {piece_name} de {from_square} para {to_square}"


def read_analyzer_game(pgn_text):
    game = chess.pgn.read_game(StringIO(pgn_text))

    if game and list(game.mainline_moves()) and not game.errors:
        return game, None

    internal_game, internal_error = read_internal_coordinate_game(pgn_text)
    if internal_game:
        return internal_game, None

    return game, internal_error


def read_internal_coordinate_game(pgn_text):
    board = chess.Board()
    game = chess.pgn.Game()
    node = game
    parsed_moves = 0

    for line_number, line in enumerate(pgn_text.splitlines(), start=1):
        line = line.strip()

        if not line:
            continue

        match = INTERNAL_MOVE_PATTERN.match(line)
        if not match:
            return None, f"A linha {line_number} não está no formato interno esperado, exemplo: 1. e2 -> e4."

        from_square, to_square, promotion_name = match.groups()
        promotion = INTERNAL_PROMOTIONS.get(promotion_name.lower()) if promotion_name else None
        move = chess.Move(
            chess.parse_square(from_square),
            chess.parse_square(to_square),
            promotion=promotion,
        )

        if move not in board.legal_moves:
            return None, f"A jogada da linha {line_number} ({from_square} -> {to_square}) é ilegal nessa posição."

        node = node.add_variation(move)
        board.push(move)
        parsed_moves += 1

    if parsed_moves == 0:
        return None, "O PGN não tem jogadas para analisar."

    return game, None


def game_analyzer(request):
    moves = []
    analysis = []
    pgn_text = ""
    error_message = ""
    opening_name = ""

    if request.method == "POST":
        pgn_text = request.POST.get("pgn", "").strip()

        game, parse_error = read_analyzer_game(pgn_text) if pgn_text else (None, None)

        if not pgn_text:
            error_message = "Cole um PGN antes de analisar a partida."
        elif not game:
            error_message = parse_error or "Não consegui ler esse PGN. Confira se ele tem jogadas em formato PGN/SAN ou no formato da sua partida."
        elif game.errors:
            error_message = "O PGN tem erros de formato ou jogadas ilegais. Corrija e tente novamente."
        elif not list(game.mainline_moves()):
            error_message = "O PGN não tem jogadas para analisar."
        elif not Path(STOCKFISH_PATH).exists():
            error_message = "Não encontrei o motor de análise na rota configurada."
        else:
            engine = None
            board = game.board()

            try:
                engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

                move_number = 1
                san_moves = []

                for move in game.mainline_moves():
                    before = engine.analyse(board, ANALYSIS_LIMIT)
                    before_score = score_to_cp(before["score"].white())

                    best_move = before.get("pv", [move])[0]
                    san = board.san(move)
                    move_description = describe_move(board, move)
                    best_description = describe_move(board, best_move)

                    san_moves.append(san)
                    opening_name = detect_opening(san_moves)

                    from_square = chess.square_name(move.from_square)
                    to_square = chess.square_name(move.to_square)

                    piece = board.piece_at(move.from_square)
                    if piece is None:
                        raise ValueError("A partida contém uma jogada que não pode ser reproduzida.")

                    piece_type = {
                        chess.PAWN: "pawn",
                        chess.KNIGHT: "horse",
                        chess.BISHOP: "bishop",
                        chess.ROOK: "rook",
                        chess.QUEEN: "queen",
                        chess.KING: "king",
                    }[piece.piece_type]

                    piece_color = "white" if piece.color == chess.WHITE else "black"

                    board.push(move)

                    after = engine.analyse(board, ANALYSIS_LIMIT)
                    after_score = score_to_cp(after["score"].white())

                    if piece_color == "white":
                        loss = before_score - after_score
                    else:
                        loss = after_score - before_score

                    loss = max(0, loss)

                    moves.append({
                        "move_number": move_number,
                        "from": from_square,
                        "to": to_square,
                        "piece_type": piece_type,
                        "piece_color": piece_color,
                        "san": san,
                    })

                    analysis.append({
                        "move_number": move_number,
                        "san": san,
                        "comment": generate_comment(loss, move_description, best_description),
                        "loss": loss,
                    })

                    move_number += 1
            except (OSError, chess.engine.EngineError, chess.engine.EngineTerminatedError, ValueError) as exc:
                moves = []
                analysis = []
                opening_name = ""
                error_message = f"Não foi possível analisar a partida: {exc}"
            finally:
                if engine:
                    try:
                        engine.quit()
                    except chess.engine.EngineTerminatedError:
                        pass

    return render(request, "games/game_analyzer.html", {
        "moves": moves,
        "analysis": analysis,
        "pgn_text": pgn_text,
        "opening_name": opening_name if moves else "",
        "error_message": error_message,
    })

def generate_comment(loss, move_description, best_description):
    if loss < 30:
        return f"Boa jogada. Eu gosto de {move_description}; mantém uma boa posição."

    if loss < 80:
        return f"Imprecisão. Eu talvez não escolheria {move_description}; minha recomendação era {best_description}."

    if loss < 180:
        return f"Erro. Eu não recomendo {move_description}, porque piora a posição. Minha recomendação era {best_description}."

    return f"Lance muito ruim. {move_description} perde muita vantagem ou material. Eu jogaria {best_description}."

