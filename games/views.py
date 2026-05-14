from django.shortcuts import render, get_object_or_404, redirect
from .models import ChessGame
from .forms import ChessGameForm
from django.contrib.auth.decorators import login_required


def home(request):
    return render(request, 'games/home.html')


def games_list(request):
    games = ChessGame.objects.all().order_by('-created_at')

    return render(request, 'games/games_list.html', {
        'games': games
    })

def game_detail(request, game_id):
    game = get_object_or_404(ChessGame, id=game_id)

    return render(request, 'games/game_detail.html', {
        'game': game
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