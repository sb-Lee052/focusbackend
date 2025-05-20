from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.db import models
from rest_framework.authtoken.models import Token


class ExpiringToken(models.Model):
    token = models.OneToOneField(
        Token,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='expiring'
    )
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.token.user.username} – last_activity: {self.last_activity}"
