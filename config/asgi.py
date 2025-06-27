
import os
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from focus.routing import websocket_urlpatterns  # WebSocket URL 패턴

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(  # 사용자 인증이 필요한 경우
        URLRouter(websocket_urlpatterns)
    ),
})
