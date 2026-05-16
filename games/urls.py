from django.urls import path
from .views import home, games_list, game_detail, game_create,save_move
from . import views


urlpatterns = [
    path('', home, name='home'),
    path('partidas/', games_list, name='games_list'),
    path('partidas/<int:game_id>/', game_detail, name='game_detail'),
    path('partidas/nova/', game_create, name='game_create'),
    path('games/<int:game_id>/save-move/', views.save_move, name='save_move'),
    path('analisar/', views.game_analyzer, name='game_analyzer'),
]