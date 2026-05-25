import uuid

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


    owner = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    white_user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='white_games')
    black_user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='black_games')
    white_guest_id = models.CharField(max_length=40, blank=True)
    black_guest_id = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=100, blank=True)
    white_player = models.CharField(max_length=100)
    black_player = models.CharField(max_length=100)
    pgn = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='unknown')
    is_rated = models.BooleanField(default=False)
    rating_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='casual')
    time_control_minutes = models.PositiveIntegerField(blank=True, null=True)
    white_time_seconds = models.PositiveIntegerField(blank=True, null=True)
    black_time_seconds = models.PositiveIntegerField(blank=True, null=True)
    active_clock_color = models.CharField(max_length=10, blank=True)
    clock_started_at = models.DateTimeField(blank=True, null=True)
    draw_offer_by_color = models.CharField(max_length=10, blank=True)

    def __str__(self):
        white = self.white_player or 'Sin asignar'
        black = self.black_player or 'Sin asignar'
        created = self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else 'Sin fecha'

        return f"Blancas: {white} vs Negras: {black} - Creada: {created}"
    
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


class DailyVisit(models.Model):
    date = models.DateField(unique=True)
    visits = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'visita diaria'
        verbose_name_plural = 'visitas diarias'

    def __str__(self):
        return f"{self.date}: {self.visits} visitas"


class GameInvitation(models.Model):
    OPPONENT_CHOICES = [
        ('direct', 'Oponente escolhido'),
        ('link', 'Convite por link'),
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

    creator = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True, related_name='sent_game_invitations')
    creator_guest_id = models.CharField(max_length=40, blank=True)
    creator_guest_name = models.CharField(max_length=100, blank=True)
    opponent = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True, related_name='received_game_invitations')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    opponent_mode = models.CharField(max_length=20, choices=OPPONENT_CHOICES)
    creator_color = models.CharField(max_length=20, choices=COLOR_CHOICES)
    is_rated = models.BooleanField(default=False)
    time_control_minutes = models.PositiveIntegerField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    game = models.ForeignKey(ChessGame, on_delete=models.SET_NULL, blank=True, null=True, related_name='invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        creator = self.creator.username if self.creator_id else (self.creator_guest_name or 'Invitado')
        return f"Convite de {creator}"


class GameChatMessage(models.Model):
    game = models.ForeignKey(ChessGame, on_delete=models.CASCADE, related_name='chat_messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True, related_name='sent_game_chat_messages')
    sender_guest_id = models.CharField(max_length=40, blank=True)
    sender_guest_name = models.CharField(max_length=100, blank=True)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        sender = self.sender.username if self.sender_id else (self.sender_guest_name or 'Invitado')
        return f"{sender}: {self.text[:40]}"


class GameChatRead(models.Model):
    game = models.ForeignKey(ChessGame, on_delete=models.CASCADE, related_name='chat_reads')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='game_chat_reads')
    last_read_message = models.ForeignKey(GameChatMessage, on_delete=models.SET_NULL, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('game', 'user')]

    def __str__(self):
        return f"{self.user.username} leu chat da partida {self.game_id}"
