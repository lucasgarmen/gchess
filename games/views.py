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