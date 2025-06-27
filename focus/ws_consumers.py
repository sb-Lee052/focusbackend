# focus/ws_consumers.py 웹소켓관련 코드 사용안하면 삭제
from channels.generic.websocket import AsyncWebsocketConsumer
import json

class DeviceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print("[WebSocket 연결 수락]")

    async def disconnect(self, close_code):
        print("[WebSocket 연결 종료]")

    async def receive(self, text_data):
        data = json.loads(text_data)
        print("[메시지 수신]", data)

        if data.get("type") == "heartbeat":
            print("[하트비트] Pi 살아있음")

        elif data.get("measure") is True:
            print("[측정 명령 수신] 라즈베리파이 측정 시작 명령 전송 필요")
            # 여기에 Flask나 라즈베리파이로 요청 보내는 코드 넣을 수 있음
