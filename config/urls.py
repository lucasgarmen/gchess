from django.contrib import admin
from django.urls import path, include
from django.templatetags.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url=static('images/favicon.png'), permanent=True)),
    path('admin/', admin.site.urls),
    path('', include('games.urls')),
    path('accounts/', include('accounts.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]
