from django.contrib import admin
from .models import ChessGame


@admin.register(ChessGame)
class ChessGameAdmin(admin.ModelAdmin):
    list_display = ('id', 'white_player', 'black_player', 'created_at', 'status', 'result')
    list_filter = ('status', 'result', 'category', 'created_at')
    search_fields = ('white_player', 'black_player', 'title')
    ordering = ('-created_at',)
