from django.urls import path
from .views import home, games_list, game_detail, game_create,save_move
from . import views


urlpatterns = [
    path('', home, name='home'),
    path('partidas/', games_list, name='games_list'),
    path('partidas/<int:game_id>/', game_detail, name='game_detail'),
    path('partidas/nova/', game_create, name='game_create'),
    path('games/<int:game_id>/save-move/', views.save_move, name='save_move'),
    path('games/<int:game_id>/mark-finished/', views.mark_finished, name='mark_finished'),
    path('analisar/', views.game_analyzer, name='game_analyzer'),
    path('engine-move/', views.engine_move, name='engine_move'),
    path('coach-analysis/', views.coach_analysis, name='coach_analysis'),
    path('trainer-chat/', views.trainer_chat, name='trainer_chat'),
]
