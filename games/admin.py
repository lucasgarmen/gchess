from django.contrib import admin
from django.db.models import Sum

from .models import ChessGame, DailyVisit


@admin.register(ChessGame)
class ChessGameAdmin(admin.ModelAdmin):
    list_display = ('id', 'white_player', 'black_player', 'created_at', 'status', 'result')
    list_filter = ('status', 'result', 'category', 'created_at')
    search_fields = ('white_player', 'black_player', 'title')
    ordering = ('-created_at',)


@admin.register(DailyVisit)
class DailyVisitAdmin(admin.ModelAdmin):
    list_display = ('date', 'visits', 'total_visits')
    date_hierarchy = 'date'
    ordering = ('-date',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='visitas totales')
    def total_visits(self, obj):
        return DailyVisit.objects.aggregate(total=Sum('visits'))['total'] or 0
