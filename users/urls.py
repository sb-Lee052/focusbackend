
from . import views
from django.urls import path
from .views import register, login_view, user_detail

urlpatterns = [
    path('register/', register, name='register'),
    path('login/',    login_view, name='login'),
    path('me/',       user_detail, name='user-detail'),
]
