from django import forms
from .models import ChessGame


class ChessGameForm(forms.ModelForm):
    class Meta:
        model = ChessGame
        fields = ['white_player', 'black_player', 'category',]