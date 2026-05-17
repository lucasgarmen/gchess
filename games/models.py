from django.db import models
from django.contrib.auth.models import User

class ChessGame(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Rascunho'),
        ('finished', 'Finalizada'),
        ('analyzing', 'Em análise'),
    ]

    RESULT_CHOICES = [
        ('white', 'Vitória das brancas'),
        ('black', 'Vitória das pretas'),
        ('draw', 'Empate'),
        ('unknown', 'Desconhecido'),
    ]
    
    CATEGORY_CHOICES = [
    ('casual', 'Casual'),
    ('ranked', 'Ranqueada'),
    ('training', 'Treino'),
]


    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    white_user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='white_games')
    black_user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='black_games')
    title = models.CharField(max_length=100, blank=True)
    white_player = models.CharField(max_length=100)
    black_player = models.CharField(max_length=100)
    pgn = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='unknown')
    rating_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='casual')
    time_control_minutes = models.PositiveIntegerField(blank=True, null=True)
    white_time_seconds = models.PositiveIntegerField(blank=True, null=True)
    black_time_seconds = models.PositiveIntegerField(blank=True, null=True)
    active_clock_color = models.CharField(max_length=10, blank=True)
    clock_started_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.title
    
class Move(models.Model):
    game = models.ForeignKey(ChessGame, on_delete=models.CASCADE, related_name='moves')
    move_number = models.PositiveIntegerField()
    from_square = models.CharField(max_length=2)
    to_square = models.CharField(max_length=2)
    piece_type = models.CharField(max_length=20)
    piece_color = models.CharField(max_length=10)
    promotion = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.move_number}. {self.from_square} -> {self.to_square}"


class UserPresence(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='presence')
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} online"


class GameInvitation(models.Model):
    OPPONENT_CHOICES = [
        ('direct', 'Oponente escolhido'),
        ('random', 'Oponente aleatório'),
    ]

    COLOR_CHOICES = [
        ('white', 'Brancas'),
        ('black', 'Pretas'),
        ('random', 'Aleatório'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('accepted', 'Aceita'),
        ('rejected', 'Recusada'),
        ('cancelled', 'Cancelada'),
    ]

    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_game_invitations')
    opponent = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True, related_name='received_game_invitations')
    opponent_mode = models.CharField(max_length=20, choices=OPPONENT_CHOICES)
    creator_color = models.CharField(max_length=20, choices=COLOR_CHOICES)
    time_control_minutes = models.PositiveIntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    game = models.ForeignKey(ChessGame, on_delete=models.SET_NULL, blank=True, null=True, related_name='invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Convite de {self.creator.username}"
