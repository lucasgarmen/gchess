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