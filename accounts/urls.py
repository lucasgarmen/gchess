from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('password_reset/', views.password_reset, name='password_reset'),
    path('password_reset/done/', views.password_reset_done, name='password_reset_done'),
    path('password_reset/confirm/<path:token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('reset/<uidb64>/<token>/', views.legacy_password_reset_link, name='legacy_password_reset_link'),
    path('password_change/', views.LocalizedPasswordChangeView.as_view(), name='password_change'),
]
