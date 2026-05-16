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
    title = models.CharField(max_length=100, blank=True)
    white_player = models.CharField(max_length=100)
    black_player = models.CharField(max_length=100)
    pgn = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='unknown')
    created_at = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='casual')

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
