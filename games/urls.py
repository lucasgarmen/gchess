from django.urls import path
from .views import home, games_list, game_detail, game_create,save_move
from . import views


urlpatterns = [
    path('', home, name='home'),
    path('idioma/', views.set_language, name='set_language'),
    path('partidas/', games_list, name='games_list'),
    path('partidas/<int:game_id>/', game_detail, name='game_detail'),
    path('partidas/nova/', game_create, name='game_create'),
    path('convites/<int:invitation_id>/aguardando/', views.game_invitation_wait, name='game_invitation_wait'),
    path('convites/<int:invitation_id>/status/', views.invitation_status, name='invitation_status'),
    path('convites/<int:invitation_id>/cancelar/', views.cancel_invitation, name='cancel_invitation'),
    path('convites/link/<uuid:token>/entrar/', views.accept_invitation_link, name='accept_invitation_link'),
    path('convites/<int:invitation_id>/aceitar/', views.accept_invitation, name='accept_invitation'),
    path('convites/<int:invitation_id>/recusar/', views.reject_invitation, name='reject_invitation'),
    path('notificacoes/partidas/', views.game_notifications, name='game_notifications'),
    path('games/<int:game_id>/save-move/', views.save_move, name='save_move'),
    path('games/<int:game_id>/mark-finished/', views.mark_finished, name='mark_finished'),
    path('games/<int:game_id>/offer-draw/', views.offer_draw, name='offer_draw'),
    path('games/<int:game_id>/answer-draw/', views.answer_draw_offer, name='answer_draw_offer'),
    path('games/<int:game_id>/resign/', views.resign_game, name='resign_game'),
    path('games/<int:game_id>/moves/', views.game_moves, name='game_moves'),
    path('games/<int:game_id>/state/', views.game_state, name='game_state'),
    path('games/<int:game_id>/state/wait/', views.game_state_wait, name='game_state_wait'),
    path('games/<int:game_id>/chat/', views.game_chat, name='game_chat'),
    path('analisar/', views.game_analyzer, name='game_analyzer'),
    path('engine-move/', views.engine_move, name='engine_move'),
    path('coach-analysis/', views.coach_analysis, name='coach_analysis'),
    path('trainer-chat/', views.trainer_chat, name='trainer_chat'),
]
