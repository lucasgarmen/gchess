from django import forms
from .models import ChessGame


class ChessGameForm(forms.ModelForm):
    class Meta:
        model = ChessGame
        fields = ['title', 'white_player', 'black_player', 'pgn', 'status', 'result']