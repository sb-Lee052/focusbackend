
from django.urls import path
from . import views
from .views import register, login_view, user_detail

urlpatterns = [
     path('register/', register),
     path('login/', login_view),
     path('me/', user_detail),
]