from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import ChessGame
from .forms import ChessGameForm
from django.contrib.auth.decorators import login_required
import json
import logging
import os
import chess
import random
import re
import shutil
from io import StringIO
from pathlib import Path
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_http_methods
from accounts.models import PlayerProfile
from .i18n import current_language, normalize_language, t
from .models import ChessGame, GameChatMessage, GameChatRead, GameInvitation, Move, UserPresence

PROMOTION_PIECES = {
    'queen': 'q',
    'rook': 'r',
    'bishop': 'b',
    'horse': 'n',
}

ONLINE_SECONDS = 60
PRESENCE_TOUCH_SECONDS = 30
ELO_K_FACTOR = 32
CLOCK_FIELDS = ['white_time_seconds', 'black_time_seconds', 'active_clock_color', 'clock_started_at', 'status', 'result']
PRESENCE_TOUCH_CACHE = {}
MAX_JSON_BODY_BYTES = 24 * 1024
MAX_ENGINE_MOVES = 300
MAX_PGN_BYTES = 80 * 1024
MAX_TRAINER_QUESTION_CHARS = 500
MAX_CHAT_MESSAGE_CHARS = 500
logger = logging.getLogger(__name__)


def rate_limit(limit, window_seconds, key_prefix):
    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                identity = f'user:{request.user.id}'
            else:
                identity = f'ip:{request.META.get("REMOTE_ADDR", "unknown")}'

            cache_key = f'rl:{key_prefix}:{identity}'
            current = cache.get(cache_key, 0)

            if current >= limit:
                return JsonResponse({'error': 'Muitas solicitações. Tente novamente em alguns instantes.'}, status=429)

            cache.set(cache_key, current + 1, window_seconds)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def parse_json_body(request):
    if len(request.body or b'') > MAX_JSON_BODY_BYTES:
        raise ValueError('Payload muito grande.')

    try:
        return json.loads(request.body or b'{}')
    except json.JSONDecodeError as exc:
        raise ValueError('JSON invalido.') from exc


def validate_moves_payload(moves):
    if not isinstance(moves, list) or len(moves) > MAX_ENGINE_MOVES:
        raise ValueError('Lista de jogadas invalida.')

    return moves


@require_POST
def set_language(request):
    request.session['language'] = normalize_language(request.POST.get('language'))
    return redirect(request.POST.get('next') or 'home')


def online_since():
    return timezone.now() - timezone.timedelta(seconds=ONLINE_SECONDS)


def touch_presence(user):
    if not user.is_authenticated:
        return

    now = timezone.now()
    cached_touch = PRESENCE_TOUCH_CACHE.get(user.id)

    if cached_touch and (now - cached_touch).total_seconds() < PRESENCE_TOUCH_SECONDS:
        return

    presence, created = UserPresence.objects.get_or_create(user=user)

    if created or (now - presence.last_seen).total_seconds() >= PRESENCE_TOUCH_SECONDS:
        UserPresence.objects.filter(id=presence.id).update(last_seen=now)
        PRESENCE_TOUCH_CACHE[user.id] = now
    else:
        PRESENCE_TOUCH_CACHE[user.id] = presence.last_seen

    PlayerProfile.objects.get_or_create(user=user)


def expected_elo_score(player_elo, opponent_elo):
    return 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))


def apply_rating_after_game(game):
    if (
        game.rating_applied or
        game.status != 'finished' or
        game.result not in ('white', 'black', 'draw') or
        not game.white_user_id or
        not game.black_user_id
    ):
        return

    white_profile, _ = PlayerProfile.objects.get_or_create(user=game.white_user)
    black_profile, _ = PlayerProfile.objects.get_or_create(user=game.black_user)

    if game.result == 'white':
        white_score = 1
        black_score = 0
    elif game.result == 'black':
        white_score = 0
        black_score = 1
    else:
        white_score = 0.5
        black_score = 0.5

    white_expected = expected_elo_score(white_profile.elo, black_profile.elo)
    black_expected = expected_elo_score(black_profile.elo, white_profile.elo)

    white_profile.elo = round(white_profile.elo + ELO_K_FACTOR * (white_score - white_expected))
    black_profile.elo = round(black_profile.elo + ELO_K_FACTOR * (black_score - black_expected))
    white_profile.save(update_fields=['elo'])
    black_profile.save(update_fields=['elo'])

    game.rating_applied = True
    game.save(update_fields=['rating_applied'])


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
    clock_settings = build_initial_clock_settings(invitation.time_control_minutes)

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
        time_control_minutes=invitation.time_control_minutes,
        **clock_settings,
    )


def build_initial_clock_settings(time_control_minutes):
    if not time_control_minutes:
        return {}

    initial_seconds = time_control_minutes * 60

    return {
        'white_time_seconds': initial_seconds,
        'black_time_seconds': initial_seconds,
        'active_clock_color': '',
        'clock_started_at': None,
    }


def clock_enabled(game):
    return bool(game.time_control_minutes)


def remaining_time_for(game, color):
    return game.white_time_seconds if color == 'white' else game.black_time_seconds


def set_remaining_time_for(game, color, seconds):
    seconds = max(0, int(seconds))

    if color == 'white':
        game.white_time_seconds = seconds
    else:
        game.black_time_seconds = seconds


def serialize_clock(game):
    if not clock_enabled(game):
        return None

    return {
        'enabled': True,
        'time_control_minutes': game.time_control_minutes,
        'white_seconds': game.white_time_seconds,
        'black_seconds': game.black_time_seconds,
        'active_color': game.active_clock_color if game.status != 'finished' else '',
        'started_at': game.clock_started_at.isoformat() if game.clock_started_at else None,
        'server_now': timezone.now().isoformat(),
        'status': game.status,
        'result': game.result,
    }


def serialize_draw_offer(game, user):
    player_color = player_color_for_game(game, user)

    if not game.draw_offer_by_color or game.status == 'finished':
        return {
            'pending': False,
            'by_color': '',
            'can_accept': False,
        }

    return {
        'pending': True,
        'by_color': game.draw_offer_by_color,
        'can_accept': bool(player_color and player_color != game.draw_offer_by_color),
    }


def finish_game(game, result):
    game.status = 'finished'
    game.result = result
    game.active_clock_color = ''
    game.clock_started_at = None
    game.draw_offer_by_color = ''
    game.save(update_fields=['status', 'result', 'active_clock_color', 'clock_started_at', 'draw_offer_by_color', 'white_time_seconds', 'black_time_seconds'])
    apply_rating_after_game(game)


def finish_game_by_timeout(game, loser):
    winner = 'black' if loser == 'white' else 'white'
    set_remaining_time_for(game, loser, 0)
    finish_game(game, winner)
    return winner


def apply_clock_elapsed(game, now=None):
    if not clock_enabled(game) or game.status == 'finished' or not game.active_clock_color:
        return None

    now = now or timezone.now()

    if not game.clock_started_at:
        game.clock_started_at = now
        game.save(update_fields=['clock_started_at'])
        return None

    elapsed_seconds = int((now - game.clock_started_at).total_seconds())

    if elapsed_seconds <= 0:
        return None

    active_color = game.active_clock_color
    remaining_seconds = remaining_time_for(game, active_color) or 0
    updated_remaining = remaining_seconds - elapsed_seconds
    set_remaining_time_for(game, active_color, updated_remaining)
    game.clock_started_at = now

    if updated_remaining <= 0:
        return finish_game_by_timeout(game, active_color)

    game.save(update_fields=[
        f'{active_color}_time_seconds',
        'clock_started_at',
    ])

    return None


def finish_clock_if_expired(game, now=None):
    if not clock_enabled(game) or game.status == 'finished' or not game.active_clock_color or not game.clock_started_at:
        return None

    now = now or timezone.now()
    elapsed_seconds = int((now - game.clock_started_at).total_seconds())
    active_color = game.active_clock_color
    remaining_seconds = remaining_time_for(game, active_color) or 0

    if elapsed_seconds >= remaining_seconds:
        return finish_game_by_timeout(game, active_color)

    return None

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

@login_required
@ensure_csrf_cookie
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
            'status': build_game_list_status(game, request.user, finished_info, current_language(request)),
            'is_finished': finished_info['finished'],
            'is_in_progress': not finished_info['finished'],
        })

    return render(request, 'games/games_list.html', {
        'game_cards': game_cards,
        'in_progress_cards': [card for card in game_cards if card['is_in_progress']],
        'finished_cards': [card for card in game_cards if card['is_finished']],
    })


def build_game_list_status(game, user, finished_info, language='pt'):
    if finished_info['finished']:
        if game.result == 'draw':
            return {
                'text': t(language, 'game_drawn'),
                'class': 'game-card-status-draw',
            }

        user_color = get_user_color_for_game(game, user)
        winner = finished_info['winner'] or game.result

        if user_color and winner in ('white', 'black'):
            return {
                'text': t(language, 'game_won') if winner == user_color else t(language, 'game_lost'),
                'class': 'game-card-status-won' if winner == user_color else 'game-card-status-lost',
            }

        return {
            'text': t(language, 'game_finished'),
            'class': 'game-card-status-finished',
        }

    moves_count = game.moves.count()
    next_turn = t(language, 'white').lower() if moves_count % 2 == 0 else t(language, 'black').lower()

    return {
        'text': f'{t(language, "game")}: {next_turn}' if language == 'en' else f'Vez das {next_turn}' if language == 'pt' else f'Turno de {next_turn}',
        'class': 'game-card-status-turn',
    }


def get_finished_game_info(game):
    if game.status == 'finished':
        return {
            'finished': True,
            'winner': game.result if game.result in ('white', 'black') else None,
            'result': game.result,
        }

    board, error = board_from_game_moves(game)

    if error:
        return {'finished': False, 'winner': None, 'result': None}

    return evaluate_board_outcome(board)


def build_chess_move(move):
    promotion = PROMOTION_PIECES.get(move.promotion or '')
    return chess.Move.from_uci(f'{move.from_square}{move.to_square}{promotion or ""}')


def build_chess_move_from_data(move_data):
    if not isinstance(move_data, dict):
        raise ValueError('Jogada invalida.')

    promotion = PROMOTION_PIECES.get(move_data.get('promotion') or '')
    return chess.Move.from_uci(f"{move_data['from']}{move_data['to']}{promotion or ''}")


def piece_type_name(piece):
    return {
        chess.PAWN: 'pawn',
        chess.KNIGHT: 'horse',
        chess.BISHOP: 'bishop',
        chess.ROOK: 'rook',
        chess.QUEEN: 'queen',
        chess.KING: 'king',
    }[piece.piece_type]


def board_from_game_moves(game):
    board = chess.Board()

    for move in game.moves.all().order_by('move_number', 'id'):
        try:
            chess_move = build_chess_move(move)
        except ValueError:
            return board, 'invalid_move'

        if chess_move not in board.legal_moves:
            return board, 'illegal_move'

        board.push(chess_move)

    return board, None


def serialize_moves(game):
    return [
        {
            'id': move.id,
            'move_number': move.move_number,
            'from': move.from_square,
            'to': move.to_square,
            'piece_type': move.piece_type,
            'piece_color': move.piece_color,
            'promotion': move.promotion,
        }
        for move in game.moves.all().order_by('move_number', 'id')
    ]


def serialize_game_state(game, user):
    board, board_error = board_from_game_moves(game)
    moves = serialize_moves(game)
    last_move = moves[-1] if moves else None
    last_saved_move = game.moves.order_by('-move_number', '-id').first()
    state_changed_at = last_saved_move.created_at if last_saved_move else game.created_at

    return {
        'game_id': game.id,
        'fen': board.fen(),
        'turn': 'white' if board.turn == chess.WHITE else 'black',
        'moves': moves,
        'move_count': len(moves),
        'last_move': last_move,
        'last_move_id': last_saved_move.id if last_saved_move else None,
        'status': game.status,
        'result': game.result if game.result in ('white', 'black', 'draw') else None,
        'game_finished': game.status == 'finished',
        'winner': game.result if game.result in ('white', 'black') else None,
        'version': f'{game.status}:{game.result}:{len(moves)}:{last_saved_move.id if last_saved_move else 0}',
        'changed_at': state_changed_at.isoformat() if state_changed_at else None,
        'board_error': board_error,
        'clock': serialize_clock(game),
        'draw_offer': serialize_draw_offer(game, user),
    }


def evaluate_board_outcome(board):
    if board.is_checkmate():
        winner = 'black' if board.turn == chess.WHITE else 'white'
        return {'finished': True, 'winner': winner, 'result': winner}

    if board.is_stalemate():
        return {'finished': True, 'winner': None, 'result': 'draw', 'reason': 'stalemate'}

    if board.is_insufficient_material():
        return {'finished': True, 'winner': None, 'result': 'draw', 'reason': 'insufficient_material'}

    if board.is_fivefold_repetition():
        return {'finished': True, 'winner': None, 'result': 'draw', 'reason': 'fivefold_repetition'}

    if board.is_seventyfive_moves():
        return {'finished': True, 'winner': None, 'result': 'draw', 'reason': 'seventyfive_moves'}

    if board.is_fifty_moves() or board.can_claim_fifty_moves():
        return {'finished': True, 'winner': None, 'result': 'draw', 'reason': 'fifty_moves'}

    if board.is_repetition(3) or board.can_claim_threefold_repetition():
        return {'finished': True, 'winner': None, 'result': 'draw', 'reason': 'threefold_repetition'}

    return {'finished': False, 'winner': None, 'result': None}


def sync_finished_game_status(game, finished_info):
    if not finished_info['finished'] or game.status == 'finished':
        return

    game.status = 'finished'

    if finished_info.get('result') in ('white', 'black', 'draw'):
        game.result = finished_info['result']

    game.save(update_fields=['status', 'result'])
    apply_rating_after_game(game)


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
    apply_clock_elapsed(game)
    player_color = player_color_for_game(game, request.user)
    moves = serialize_moves(game)

    return render(request, 'games/game_detail.html', {
        'game': game,
        'moves': moves,
        'player_color': player_color,
        'multiplayer_mode': bool(game.white_user_id and game.black_user_id),
        'clock': serialize_clock(game),
        'draw_offer': serialize_draw_offer(game, request.user),
    })

@login_required   
def game_create(request):
    touch_presence(request.user)
    if request.method == 'POST':
        form = ChessGameForm(request.POST, language=current_language(request))

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
                        time_control_minutes=form.cleaned_data['time_control_minutes'],
                    )
                    return redirect('game_invitation_wait', invitation_id=invitation.id)
            elif opponent_mode == 'link':
                invitation = GameInvitation.objects.create(
                    creator=request.user,
                    opponent_mode='link',
                    creator_color=form.cleaned_data['color_choice'],
                    time_control_minutes=form.cleaned_data['time_control_minutes'],
                )
                return redirect('game_invitation_wait', invitation_id=invitation.id)
            else:
                invitation = GameInvitation.objects.create(
                    creator=request.user,
                    opponent_mode='random',
                    creator_color=form.cleaned_data['color_choice'],
                    time_control_minutes=form.cleaned_data['time_control_minutes'],
                )
                return redirect('game_invitation_wait', invitation_id=invitation.id)
    else:
        form = ChessGameForm(language=current_language(request))

    return render(request, 'games/game_create.html', {
        'form': form
    })
    
@login_required
@require_POST
@rate_limit(60, 60, 'save-move')
@transaction.atomic
def save_move(request, game_id):
    touch_presence(request.user)
    game = get_object_or_404(
        ChessGame.objects.select_for_update(),
        game_access_filter(request.user),
        id=game_id,
    )
    try:
        data = parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    timeout_winner = apply_clock_elapsed(game)

    if timeout_winner:
        logger.info("Move rejected for game %s by user %s: clock expired.", game.id, request.user.id)
        return JsonResponse({
            'error': 'Tempo esgotado.',
            'clock': serialize_clock(game),
            'game_finished': True,
            'winner': timeout_winner,
        }, status=409)

    player_color = player_color_for_game(game, request.user)
    expected_color = 'white' if game.moves.count() % 2 == 0 else 'black'

    if game.status == 'finished':
        logger.info("Move rejected for game %s by user %s: game is finished.", game.id, request.user.id)
        return JsonResponse({'error': 'A partida ja terminou.'}, status=409)

    if not player_color:
        logger.warning("Move rejected for game %s by user %s: user is not a player.", game.id, request.user.id)
        return JsonResponse({'error': 'Apenas jogadores da partida podem mover.'}, status=403)

    if player_color != expected_color:
        logger.info("Move rejected for game %s by user %s: expected %s, got %s.", game.id, request.user.id, expected_color, player_color)
        return JsonResponse({'error': 'Nao e sua vez.'}, status=403)

    board, board_error = board_from_game_moves(game)

    if board_error:
        logger.warning("Move rejected for game %s by user %s: saved board is invalid (%s).", game.id, request.user.id, board_error)
        return JsonResponse({'error': 'A posicao salva da partida esta invalida.'}, status=409)

    try:
        chess_move = build_chess_move_from_data(data)
    except (KeyError, ValueError):
        logger.info("Move rejected for game %s by user %s: invalid payload.", game.id, request.user.id)
        return JsonResponse({'error': 'Jogada invalida.'}, status=400)

    if chess_move not in board.legal_moves:
        logger.info("Move rejected for game %s by user %s: illegal move %s.", game.id, request.user.id, chess_move)
        return JsonResponse({'error': 'Jogada ilegal nessa posicao.'}, status=400)

    moving_piece = board.piece_at(chess_move.from_square)

    if not moving_piece:
        logger.info("Move rejected for game %s by user %s: no piece at origin.", game.id, request.user.id)
        return JsonResponse({'error': 'Jogada invalida.'}, status=400)

    server_piece_color = 'white' if moving_piece.color == chess.WHITE else 'black'

    if server_piece_color != expected_color:
        logger.info("Move rejected for game %s by user %s: attempted color %s on %s turn.", game.id, request.user.id, server_piece_color, expected_color)
        return JsonResponse({'error': 'Nao e a vez dessa cor.'}, status=400)

    if server_piece_color != player_color:
        logger.warning("Move rejected for game %s by user %s: attempted opponent color %s.", game.id, request.user.id, server_piece_color)
        return JsonResponse({'error': 'Voce so pode mover suas proprias pecas.'}, status=403)

    draw_offer_declined_by_move = bool(
        game.draw_offer_by_color and game.draw_offer_by_color != server_piece_color
    )

    move = Move.objects.create(
        game=game,
        move_number=game.moves.count() + 1,
        from_square=chess.square_name(chess_move.from_square),
        to_square=chess.square_name(chess_move.to_square),
        piece_type=piece_type_name(moving_piece),
        piece_color=server_piece_color,
        promotion=data.get('promotion') if data.get('promotion') in PROMOTION_PIECES else None,
    )

    board.push(chess_move)
    outcome = evaluate_board_outcome(board)

    if outcome['finished']:
        game.status = 'finished'
        game.active_clock_color = ''
        game.clock_started_at = None
        game.draw_offer_by_color = ''

        if outcome.get('result') in ('white', 'black', 'draw'):
            game.result = outcome['result']

        game.save(update_fields=['status', 'result', 'active_clock_color', 'clock_started_at', 'draw_offer_by_color'])
        apply_rating_after_game(game)
    elif clock_enabled(game):
        game.active_clock_color = 'black' if expected_color == 'white' else 'white'
        game.clock_started_at = timezone.now()
        update_fields = ['active_clock_color', 'clock_started_at']

        if draw_offer_declined_by_move:
            game.draw_offer_by_color = ''
            update_fields.append('draw_offer_by_color')

        game.save(update_fields=update_fields)
    elif draw_offer_declined_by_move:
        game.draw_offer_by_color = ''
        game.save(update_fields=['draw_offer_by_color'])

    logger.info(
        "Move saved for game %s by user %s: %s%s.",
        game.id,
        request.user.id,
        move.from_square,
        move.to_square,
    )

    return JsonResponse({
        'status': 'ok',
        'move_id': move.id,
        'clock': serialize_clock(game),
        'game_finished': game.status == 'finished',
        'winner': game.result if game.result in ('white', 'black') else None,
        'result': game.result if game.result in ('white', 'black', 'draw') else None,
        'draw_reason': outcome.get('reason'),
        'draw_offer': serialize_draw_offer(game, request.user),
    })


@login_required
@require_POST
@rate_limit(20, 60, 'mark-finished')
def mark_finished(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)

    try:
        data = parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if data.get('reason') == 'timeout' and data.get('loser') in ('white', 'black'):
        apply_clock_elapsed(game)

        if game.status != 'finished':
            remaining_seconds = remaining_time_for(game, data['loser'])

            if remaining_seconds is None or remaining_seconds > 0:
                return JsonResponse({
                    'error': 'O tempo ainda nÃ£o acabou.',
                    'clock': serialize_clock(game),
                }, status=409)

            finish_game_by_timeout(game, data['loser'])

        return JsonResponse({
            'status': 'ok',
            'clock': serialize_clock(game),
            'game_finished': True,
            'winner': game.result if game.result in ('white', 'black') else None,
            'result': game.result,
        })

    board, board_error = board_from_game_moves(game)

    if board_error:
        return JsonResponse({'error': 'A posicao salva da partida esta invalida.'}, status=409)

    outcome = evaluate_board_outcome(board)

    if not outcome['finished']:
        return JsonResponse({'error': 'A partida ainda nao terminou no servidor.'}, status=409)

    game.status = 'finished'
    game.result = outcome['result']
    game.active_clock_color = ''
    game.clock_started_at = None
    game.draw_offer_by_color = ''
    game.save(update_fields=['status', 'result', 'active_clock_color', 'clock_started_at', 'draw_offer_by_color'])
    apply_rating_after_game(game)

    return JsonResponse({
        'status': 'ok',
        'clock': serialize_clock(game),
        'result': game.result,
        'game_finished': game.status == 'finished',
        'winner': game.result if game.result in ('white', 'black') else None,
        'draw_offer': serialize_draw_offer(game, request.user),
    })


@login_required
@require_POST
@rate_limit(20, 60, 'offer-draw')
def offer_draw(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)
    player_color = player_color_for_game(game, request.user)

    if game.status == 'finished':
        return JsonResponse({'error': 'A partida ja terminou.'}, status=409)

    if not player_color:
        return JsonResponse({'error': 'Apenas jogadores da partida podem oferecer empate.'}, status=403)

    if game.draw_offer_by_color and game.draw_offer_by_color != player_color:
        finish_game(game, 'draw')
        return JsonResponse({
            'status': 'accepted',
            'game_finished': True,
            'result': 'draw',
            'draw_offer': serialize_draw_offer(game, request.user),
            'clock': serialize_clock(game),
        })

    game.draw_offer_by_color = player_color
    game.save(update_fields=['draw_offer_by_color'])

    return JsonResponse({
        'status': 'offered',
        'draw_offer': serialize_draw_offer(game, request.user),
    })


@login_required
@require_POST
@rate_limit(20, 60, 'answer-draw')
def answer_draw_offer(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)
    player_color = player_color_for_game(game, request.user)
    try:
        data = parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    accepted = bool(data.get('accepted'))

    if game.status == 'finished':
        return JsonResponse({'error': 'A partida ja terminou.'}, status=409)

    if not player_color:
        return JsonResponse({'error': 'Apenas jogadores da partida podem responder.'}, status=403)

    if not game.draw_offer_by_color:
        return JsonResponse({'error': 'Nao ha oferta de empate pendente.'}, status=409)

    if game.draw_offer_by_color == player_color:
        return JsonResponse({'error': 'Voce nao pode aceitar sua propria oferta.'}, status=403)

    if accepted:
        finish_game(game, 'draw')
        return JsonResponse({
            'status': 'accepted',
            'game_finished': True,
            'result': 'draw',
            'draw_offer': serialize_draw_offer(game, request.user),
            'clock': serialize_clock(game),
        })

    game.draw_offer_by_color = ''
    game.save(update_fields=['draw_offer_by_color'])

    return JsonResponse({
        'status': 'rejected',
        'draw_offer': serialize_draw_offer(game, request.user),
    })


@login_required
@require_POST
@rate_limit(10, 60, 'resign')
def resign_game(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)
    player_color = player_color_for_game(game, request.user)

    if game.status == 'finished':
        return JsonResponse({'error': 'A partida ja terminou.'}, status=409)

    if not player_color:
        return JsonResponse({'error': 'Apenas jogadores da partida podem desistir.'}, status=403)

    winner = 'black' if player_color == 'white' else 'white'
    finish_game(game, winner)

    return JsonResponse({
        'status': 'resigned',
        'game_finished': True,
        'winner': winner,
        'result': winner,
        'draw_offer': serialize_draw_offer(game, request.user),
        'clock': serialize_clock(game),
    })


@login_required
def game_invitation_wait(request, invitation_id):
    touch_presence(request.user)
    invitation = get_object_or_404(GameInvitation, id=invitation_id, creator=request.user)
    invitation_accept_url = request.build_absolute_uri(
        reverse('accept_invitation_link', args=[invitation.token])
    )

    return render(request, 'games/game_invitation_wait.html', {
        'invitation': invitation,
        'invitation_accept_url': invitation_accept_url,
    })


@login_required
def invitation_status(request, invitation_id):
    touch_presence(request.user)
    invitation = get_object_or_404(GameInvitation, id=invitation_id, creator=request.user)

    response = JsonResponse({
        'status': invitation.status,
        'game_id': invitation.game_id,
        'game_url': f'/partidas/{invitation.game_id}/' if invitation.game_id else None,
    })
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


@login_required
@require_POST
@rate_limit(20, 60, 'cancel-invitation')
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
@rate_limit(120, 60, 'game-notifications')
def game_notifications(request):
    touch_presence(request.user)
    language = current_language(request)
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
                'time_control_minutes': invitation.time_control_minutes,
                'label': (
                    f"{invitation.creator.username} procura um oponente aleatório."
                    if invitation.opponent_mode == 'random'
                    else f"{invitation.creator.username} convidou você para jogar."
                ) if language == 'pt' else (
                    f"{invitation.creator.username} busca un oponente aleatorio."
                    if invitation.opponent_mode == 'random'
                    else f"{invitation.creator.username} te invitó a jugar."
                ) if language == 'es' else (
                    f"{invitation.creator.username} is looking for a random opponent."
                    if invitation.opponent_mode == 'random'
                    else f"{invitation.creator.username} invited you to play."
                ),
            }
            for invitation in invitations
        ]
    })


@login_required
@require_POST
@rate_limit(20, 60, 'accept-invitation')
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

        invitation = GameInvitation.objects.select_related('creator', 'opponent').get(id=invitation.id)
        game = create_game_from_invitation(invitation, request.user)
        invitation.game = game
        invitation.save(update_fields=['game'])

    return JsonResponse({
        'status': 'accepted',
        'game_id': game.id,
        'game_url': f'/partidas/{game.id}/',
    })


@login_required
@rate_limit(20, 60, 'accept-link')
def accept_invitation_link(request, token):
    touch_presence(request.user)

    with transaction.atomic():
        invitation = get_object_or_404(GameInvitation, token=token, opponent_mode='link')

        if invitation.creator_id == request.user.id:
            return redirect('game_invitation_wait', invitation_id=invitation.id)

        if invitation.status != 'pending':
            if invitation.game_id and (
                invitation.opponent_id == request.user.id or invitation.creator_id == request.user.id
            ):
                return redirect('game_detail', game_id=invitation.game_id)

            return redirect('games_list')

        if invitation.opponent_id and invitation.opponent_id != request.user.id:
            return redirect('games_list')

        accepted_count = GameInvitation.objects.filter(
            id=invitation.id,
            status='pending',
            opponent_mode='link',
            opponent__isnull=True,
        ).exclude(
            creator=request.user
        ).update(
            opponent=request.user,
            status='accepted',
            responded_at=timezone.now(),
        )

        if accepted_count == 0:
            return redirect('games_list')

        invitation = GameInvitation.objects.select_related('creator', 'opponent').get(id=invitation.id)
        game = create_game_from_invitation(invitation, request.user)
        invitation.game = game
        invitation.save(update_fields=['game'])

    return redirect('game_detail', game_id=game.id)


@login_required
@require_POST
@rate_limit(20, 60, 'reject-invitation')
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
@rate_limit(120, 60, 'game-moves')
def game_moves(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)
    finish_clock_if_expired(game)

    return JsonResponse({
        'moves': serialize_moves(game),
        'clock': serialize_clock(game),
        'game_finished': game.status == 'finished',
        'winner': game.result if game.result in ('white', 'black') else None,
        'result': game.result if game.result in ('white', 'black', 'draw') else None,
        'draw_offer': serialize_draw_offer(game, request.user),
    })


@login_required
@rate_limit(120, 60, 'game-state')
def game_state(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)
    finish_clock_if_expired(game)
    state = serialize_game_state(game, request.user)

    logger.info(
        "[polling] game_state game_id=%s user_id=%s move_count=%s last_move_id=%s turn=%s fen=%s",
        state['game_id'],
        request.user.id,
        state['move_count'],
        state['last_move_id'],
        state['turn'],
        state['fen'],
    )

    response = JsonResponse(state)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    return response


@login_required
@require_http_methods(["GET", "POST"])
@rate_limit(120, 60, 'game-chat')
def game_chat(request, game_id):
    touch_presence(request.user)
    game = get_game_for_user(game_id, request.user)

    if not player_color_for_game(game, request.user):
        return JsonResponse({'error': 'Apenas jogadores da partida podem usar o chat.'}, status=403)

    if request.method == 'POST':
        try:
            data = parse_json_body(request)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        text = (data.get('text') or '').strip()

        if not text:
            return JsonResponse({'error': 'Digite uma mensagem.'}, status=400)

        if len(text) > MAX_CHAT_MESSAGE_CHARS:
            return JsonResponse({'error': 'Mensagem muito longa.'}, status=400)

        GameChatMessage.objects.create(
            game=game,
            sender=request.user,
            text=text,
        )

    messages = list(
        GameChatMessage.objects.filter(game=game)
        .select_related('sender')
        .order_by('created_at', 'id')[:100]
    )
    latest_message = messages[-1] if messages else None
    read_state, _ = GameChatRead.objects.get_or_create(game=game, user=request.user)

    if request.GET.get('mark_read') == '1' and latest_message:
        read_state.last_read_message = latest_message
        read_state.save(update_fields=['last_read_message', 'updated_at'])

    unread_query = GameChatMessage.objects.filter(game=game).exclude(sender=request.user)

    if read_state.last_read_message_id:
        unread_query = unread_query.filter(id__gt=read_state.last_read_message_id)

    return JsonResponse({
        'messages': [
            {
                'id': message.id,
                'sender': message.sender.username,
                'mine': message.sender_id == request.user.id,
                'text': message.text,
                'created_at': timezone.localtime(message.created_at).strftime('%H:%M'),
            }
            for message in messages
        ],
        'unread_count': unread_query.count(),
    })

import chess.pgn
import chess.engine

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


def configured_stockfish_path():
    stockfish_path = os.getenv("STOCKFISH_PATH", "").strip()

    if not stockfish_path:
        discovered_path = shutil.which("stockfish")

        if discovered_path:
            logger.info("Using Stockfish found on PATH: %s", discovered_path)
            return discovered_path, ""

        return "", "STOCKFISH_PATH is not configured and stockfish was not found on PATH."

    if Path(stockfish_path).exists():
        return stockfish_path, ""

    discovered_path = shutil.which(stockfish_path)

    if discovered_path:
        logger.info("Using Stockfish from STOCKFISH_PATH: %s", discovered_path)
        return discovered_path, ""

    fallback_path = shutil.which("stockfish")

    if fallback_path:
        logger.warning(
            "STOCKFISH_PATH=%r was not found. Falling back to Stockfish on PATH: %s",
            stockfish_path,
            fallback_path,
        )
        return fallback_path, ""

    for common_path in ("/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"):
        if Path(common_path).exists():
            logger.warning(
                "STOCKFISH_PATH=%r was not found. Falling back to Stockfish at: %s",
                stockfish_path,
                common_path,
            )
            return common_path, ""

    return "", f"Stockfish was not found at STOCKFISH_PATH={stockfish_path!r}."


def stockfish_is_configured():
    _stockfish_path, error_message = configured_stockfish_path()
    return not error_message


def stockfish_missing_response(error_message=""):
    if not error_message:
        _stockfish_path, error_message = configured_stockfish_path()

    logger.warning("Stockfish unavailable: %s", error_message)
    return JsonResponse({
        "error": (
            "Stockfish is not available. Check the STOCKFISH_PATH environment variable "
            f"and make sure the executable exists. Detail: {error_message}"
        ),
    }, status=503)

@login_required
@require_POST
@rate_limit(30, 60, 'engine-move')
def engine_move(request):
    try:
        data = parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    try:
        moves = validate_moves_payload(data.get("moves", []))
        elo = int(data.get("elo", 1200))
    except (TypeError, ValueError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    if elo not in (500, 800, 1000, 1320, 1600, 2000, 2500):
        return JsonResponse({'error': 'Elo invalido.'}, status=400)

    board = chess.Board()

    try:
        for move_data in moves:
            move = build_move_from_data(move_data)

            if move not in board.legal_moves:
                return JsonResponse({"error": "A partida contém uma jogada ilegal."}, status=400)

            board.push(move)
    except (KeyError, ValueError):
        return JsonResponse({"error": "Nao consegui ler as jogadas."}, status=400)

    if board.is_game_over():
        return JsonResponse({
            "error": "A partida já terminou.",
        }, status=400)

    stockfish_path, stockfish_error = configured_stockfish_path()
    if stockfish_error:
        return stockfish_missing_response(stockfish_error)

    engine = None
    try:
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
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
        logger.exception("Stockfish failed while calculating an engine move.")
        return JsonResponse({
            "error": f"Não foi possível calcular a jogada: {exc}",
        }, status=500)

    finally:
        if engine:
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


@login_required
@require_POST
@rate_limit(20, 60, 'coach-analysis')
def coach_analysis(request):
    try:
        data = parse_json_body(request)
        moves = validate_moves_payload(data.get("moves", []))
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    player_color = data.get("player_color", "white")
    language = normalize_language(data.get("language") or current_language(request))

    if player_color not in ('white', 'black'):
        return JsonResponse({'error': 'Cor invalida.'}, status=400)

    if not moves:
        return JsonResponse({
            "error": "Não há jogadas para analisar.",
        }, status=400)

    stockfish_path, stockfish_error = configured_stockfish_path()
    if stockfish_error:
        return stockfish_missing_response(stockfish_error)

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

    engine = None
    try:
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
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
                language,
            ),
            "loss": loss,
            "played": played_san,
            "best": best_san,
        })
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError) as exc:
        logger.exception("Stockfish failed while analyzing a coach move.")
        return JsonResponse({
            "error": f"Não foi possível analisar a jogada: {exc}",
        }, status=500)
    finally:
        if engine:
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


@login_required
@require_POST
@rate_limit(20, 60, 'trainer-chat')
def trainer_chat(request):
    try:
        data = parse_json_body(request)
        moves = validate_moves_payload(data.get("moves", []))
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    question = data.get("question", "").strip()
    player_color = data.get("player_color", "white")
    language = normalize_language(data.get("language") or current_language(request))

    if player_color not in ('white', 'black'):
        return JsonResponse({'error': 'Cor invalida.'}, status=400)

    if len(question) > MAX_TRAINER_QUESTION_CHARS:
        return JsonResponse({'error': 'Pergunta muito longa.'}, status=400)

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

    stockfish_path, stockfish_error = configured_stockfish_path()
    if stockfish_error:
        return stockfish_missing_response(stockfish_error)

    engine = None
    try:
        engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        answer = build_trainer_chat_answer(engine, board, san_moves, question, player_color, language)

        return JsonResponse({
            "answer": answer,
        })
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError) as exc:
        logger.exception("Stockfish failed while answering trainer chat.")
        return JsonResponse({
            "error": f"Não foi possível responder agora: {exc}",
        }, status=500)
    finally:
        if engine:
            engine.quit()


def build_trainer_chat_answer(engine, board, san_moves, question, player_color, language='pt'):
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

    if language == 'es':
        if player_is_to_move:
            return (
                f"Yo consideraría {best_san}. La idea principal es mejorar la actividad, "
                "cuidar las piezas indefensas y controlar casillas importantes."
            )

        return (
            f"Ahora juega el rival. La continuación indicada por el motor es {best_san}; "
            "mira qué amenaza crea y qué piezas quedan atacadas."
        )

    if language == 'en':
        if player_is_to_move:
            return (
                f"I would consider {best_san}. The main idea is to improve activity, "
                "watch undefended pieces, and control key squares."
            )

        return (
            f"It is your opponent's turn. The engine points to {best_san}; "
            "watch the threat it creates and which pieces are attacked."
        )

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


def coach_comment(loss, board, played_move, best_move, played_san, best_san, before_score, after_score, language='pt'):
    if language == 'es':
        if loss < 30:
            return f"Buena jugada: {played_san}. La posición se mantiene sana. Sigue mirando piezas atacadas y seguridad del rey."
        if loss < 80:
            return f"Imprecisión: {played_san}. Yo consideraría {best_san}, que mantiene mejor la coordinación."
        if loss < 180:
            return f"Error: {played_san} empeora la posición. Mejor era {best_san}, con más actividad o menos riesgo."
        return f"Jugada muy mala: {played_san} pierde mucha fuerza. La recomendación era {best_san}."

    if language == 'en':
        if loss < 30:
            return f"Good move: {played_san}. The position stays healthy. Keep checking attacked pieces and king safety."
        if loss < 80:
            return f"Inaccuracy: {played_san}. I would consider {best_san}, which keeps better coordination."
        if loss < 180:
            return f"Mistake: {played_san} worsens the position. Better was {best_san}, with more activity or less risk."
        return f"Very bad move: {played_san} loses a lot of strength. The recommendation was {best_san}."

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


@login_required
@rate_limit(12, 60, 'game-analyzer')
def game_analyzer(request):
    language = current_language(request)
    moves = []
    analysis = []
    pgn_text = ""
    error_message = ""
    opening_name = ""

    if request.method == "POST":
        pgn_text = request.POST.get("pgn", "").strip()

        game, parse_error = read_analyzer_game(pgn_text) if pgn_text and len(pgn_text.encode('utf-8')) <= MAX_PGN_BYTES else (None, None)
        stockfish_path, stockfish_error = configured_stockfish_path()

        if not pgn_text:
            error_message = "Cole um PGN antes de analisar a partida."
        elif len(pgn_text.encode('utf-8')) > MAX_PGN_BYTES:
            error_message = "O PGN e muito grande para analisar de uma vez."
        elif not game:
            error_message = parse_error or "Não consegui ler esse PGN. Confira se ele tem jogadas em formato PGN/SAN ou no formato da sua partida."
        elif game.errors:
            error_message = "O PGN tem erros de formato ou jogadas ilegais. Corrija e tente novamente."
        elif not list(game.mainline_moves()):
            error_message = "O PGN não tem jogadas para analisar."
        elif stockfish_error:
            logger.warning("Stockfish unavailable for PGN analyzer: %s", stockfish_error)
            error_message = "Não encontrei o motor de análise na rota configurada."
        else:
            engine = None
            board = game.board()

            try:
                engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)

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
                        "comment": generate_comment(loss, move_description, best_description, language),
                        "loss": loss,
                    })

                    move_number += 1
            except (OSError, chess.engine.EngineError, chess.engine.EngineTerminatedError, ValueError) as exc:
                logger.exception("Stockfish failed while analyzing a PGN.")
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

def generate_comment(loss, move_description, best_description, language='pt'):
    if language == 'es':
        if loss < 30:
            return "Buena jugada. Mantiene una posición sana."
        if loss < 80:
            return "Imprecisión. Había una continuación más precisa según el motor."
        if loss < 180:
            return "Error. La jugada empeora la posición; conviene revisar la recomendación del motor."
        return "Jugada muy mala. Pierde demasiada ventaja o material."

    if language == 'en':
        if loss < 30:
            return "Good move. It keeps a healthy position."
        if loss < 80:
            return "Inaccuracy. The engine found a more precise continuation."
        if loss < 180:
            return "Mistake. The move worsens the position; check the engine recommendation."
        return "Very bad move. It loses too much advantage or material."

    if loss < 30:
        return f"Boa jogada. Eu gosto de {move_description}; mantém uma boa posição."

    if loss < 80:
        return f"Imprecisão. Eu talvez não escolheria {move_description}; minha recomendação era {best_description}."

    if loss < 180:
        return f"Erro. Eu não recomendo {move_description}, porque piora a posição. Minha recomendação era {best_description}."

    return f"Lance muito ruim. {move_description} perde muita vantagem ou material. Eu jogaria {best_description}."

