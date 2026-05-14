from django.urls import path
from .views import home, games_list, game_detail, game_create

urlpatterns = [
    path('', home, name='home'),
    path('partidas/', games_list, name='games_list'),
    path('partidas/<int:game_id>/', game_detail, name='game_detail'),
    path('partidas/nova/', game_create, name='game_create'),
]