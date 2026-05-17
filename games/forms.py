from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from .models import ChessGame


ONLINE_SECONDS = 60


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

    time_control_minutes = forms.IntegerField(
        label='Tempo por jogador (minutos)',
        required=False,
        min_value=1,
        max_value=5000,
        widget=forms.NumberInput(attrs={
            'class': 'time-control-input',
            'placeholder': 'Livre',
            'min': '1',
            'max': '5000',
            'step': '1',
        }),
    )

    def clean_opponent_name(self):
        return self.cleaned_data['opponent_name'].strip()

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get('opponent_mode') == 'choose' and not cleaned_data.get('opponent_name'):
            self.add_error('opponent_name', 'Informe o nome do oponente.')

        time_control = cleaned_data.get('time_control_minutes')

        if not time_control:
            cleaned_data['time_control_minutes'] = None

        return cleaned_data

    def get_opponent_user(self):
        if self.cleaned_data.get('opponent_mode') != 'choose':
            return None

        username = self.cleaned_data.get('opponent_name')
        online_since = timezone.now() - timezone.timedelta(seconds=ONLINE_SECONDS)

        return User.objects.filter(
            username__iexact=username,
            presence__last_seen__gte=online_since,
        ).first()
