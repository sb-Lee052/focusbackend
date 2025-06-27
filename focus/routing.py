from django.urls import path
from .ws_consumers import DeviceConsumer

websocket_urlpatterns = [
    path("ws/device/", DeviceConsumer.as_asgi()),
]
