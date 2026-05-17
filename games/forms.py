from django import forms
from .models import ChessGame


class ChessGameForm(forms.Form):
    opponent_mode = forms.ChoiceField(
        label='Oponente',
        choices=[
            ('random', 'Aleatório'),
            ('choose', 'Escolher oponente'),
        ],
        initial='random',
        widget=forms.RadioSelect,
    )
    opponent_name = forms.CharField(
        label='Nome do oponente',
        max_length=100,
        required=False,
    )
    color_choice = forms.ChoiceField(
        label='Cor das peças',
        choices=[
            ('white', 'Brancas'),
            ('black', 'Pretas'),
            ('random', 'Aleatório'),
        ],
        initial='random',
        widget=forms.RadioSelect,
    )

    def clean_opponent_name(self):
        return self.cleaned_data['opponent_name'].strip()

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get('opponent_mode') == 'choose' and not cleaned_data.get('opponent_name'):
            self.add_error('opponent_name', 'Informe o nome do oponente.')

        return cleaned_data
