from django.shortcuts import render, get_object_or_404, redirect
from .models import ChessGame
from .forms import ChessGameForm
from django.contrib.auth.decorators import login_required
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import ChessGame, Move

def home(request):
    return render(request, 'games/home.html')


def games_list(request):
    games = ChessGame.objects.all().order_by('-created_at')

    return render(request, 'games/games_list.html', {
        'games': games
    })

def game_detail(request, game_id):
    game = ChessGame.objects.get(id=game_id)

    moves = [
        {
            'move_number': move.move_number,
            'from': move.from_square,
            'to': move.to_square,
            'piece_type': move.piece_type,
            'piece_color': move.piece_color,
        }
        for move in game.moves.all().order_by('move_number')
    ]

    return render(request, 'games/game_detail.html', {
        'game': game,
        'moves': moves,
    })

@login_required   
def game_create(request):
    if request.method == 'POST':
        form = ChessGameForm(request.POST)

        if form.is_valid():
            game = form.save(commit=False)
            game.owner = request.user
            game.save()
            return redirect('games_list')
    else:
        form = ChessGameForm()

    return render(request, 'games/game_create.html', {
        'form': form
    })
    
@require_POST
def save_move(request, game_id):
    game = ChessGame.objects.get(id=game_id)

    data = json.loads(request.body)

    move = Move.objects.create(
        game=game,
        move_number=data['move_number'],
        from_square=data['from'],
        to_square=data['to'],
        piece_type=data['piece_type'],
        piece_color=data['piece_color'],
    )

    return JsonResponse({
        'status': 'ok',
        'move_id': move.id
    })

import chess.pgn
import chess.engine
from io import StringIO
from pathlib import Path

STOCKFISH_PATH = r"C:\Users\lucas\Downloads\stockfish-windows-x86-64-avx2\stockfish\stockfish-windows-x86-64-avx2.exe"
ANALYSIS_LIMIT = chess.engine.Limit(time=0.05)


def classify_move(loss):
    if loss is None:
        return "Jugada analisada."

    if loss < 30:
        return "Boa jogada."
    elif loss < 80:
        return "Imprecisão."
    elif loss < 180:
        return "Erro."
    else:
        return "Blunder."


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

def game_analyzer(request):
    moves = []
    analysis = []
    pgn_text = ""
    error_message = ""
    opening_name = ""

    if request.method == "POST":
        pgn_text = request.POST.get("pgn", "").strip()

        game = chess.pgn.read_game(StringIO(pgn_text))

        if not pgn_text:
            error_message = "Pega un PGN antes de analizar la partida."
        elif not game:
            error_message = "No pude leer ese PGN. Revisa que tenga jugadas en formato PGN/SAN."
        elif game.errors:
            error_message = "El PGN tiene errores de formato o jugadas ilegales. Corrigelo e intenta otra vez."
        elif not list(game.mainline_moves()):
            error_message = "El PGN no tiene jugadas para analizar."
        elif not Path(STOCKFISH_PATH).exists():
            error_message = "No encontre Stockfish en la ruta configurada."
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
                    best_san = board.san(best_move)
                    san = board.san(move)

                    san_moves.append(san)
                    opening_name = detect_opening(san_moves)

                    from_square = chess.square_name(move.from_square)
                    to_square = chess.square_name(move.to_square)

                    piece = board.piece_at(move.from_square)
                    if piece is None:
                        raise ValueError("La partida contiene una jugada que no se puede reproducir.")

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
                        "comment": generate_comment(loss, san, best_san),
                        "loss": loss,
                    })

                    move_number += 1
            except (OSError, chess.engine.EngineError, chess.engine.EngineTerminatedError, ValueError) as exc:
                moves = []
                analysis = []
                opening_name = ""
                error_message = f"No se pudo analizar la partida: {exc}"
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

def generate_comment(loss, san, best_san):
    if loss < 30:
        return f"Boa jogada. {san} mantém uma boa posição."

    if loss < 80:
        return f"Imprecisão. {san} não é ruim, mas {best_san} parecia mais preciso."

    if loss < 180:
        return f"Erro. {san} piora a posição. Stockfish preferia {best_san}."

    return f"Blunder. {san} perde muita vantagem ou material. Melhor era {best_san}."
