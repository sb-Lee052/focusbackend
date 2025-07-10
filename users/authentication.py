# users/authentication.py
from datetime import timedelta
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework import exceptions
from .models import ExpiringToken

EXPIRE_MINUTES = 120

class SlidingTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        # 부모 로직으로 (user, token) 가져오기
        user, token = super().authenticate_credentials(key)

        # ExpiringToken 레코드가 없다면 생성
        et, _ = ExpiringToken.objects.get_or_create(token=token)

        # 만료 검사
        if timezone.now() - et.last_activity > timedelta(minutes=EXPIRE_MINUTES):
            # 실제 토큰도 같이 삭제
            token.delete()
            et.delete()
            raise exceptions.AuthenticationFailed('토큰이 만료되었습니다.')

        # 갱신: auto_now로 last_activity 업데이트
        et.save()

        return (user, token)
