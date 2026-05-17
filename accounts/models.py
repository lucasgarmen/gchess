from django.db import models
from django.contrib.auth.models import User


class PlayerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='player_profile')
    elo = models.IntegerField(default=1200)

    def __str__(self):
        return f"{self.user.username} ({self.elo})"
