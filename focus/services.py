# focus/services.py
import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone
from django.core.mail import send_mail
from celery import shared_task
from django.contrib.auth import get_user_model
from datetime import timedelta
from .models import FaceLostEvent, FocusData

def fetch_and_save_face_lost_summary(date_str, user):
    """
    외부 API (/focus/face_lost_summary/) 에서 face_lost summary를 받아
    FaceLostEvent 모델에 저장합니다.
    """
    base = getattr(settings, 'API_BASE_URL', None)
    token = getattr(settings, 'API_TOKEN', None)
    if not base or not token:
        raise ImproperlyConfigured("API_BASE_URL/API_TOKEN 설정이 필요합니다.")

    url = f"{base}/focus/face_lost_summary/"
    headers = {'Authorization': f'Token {token}'}
    params = {'date': date_str}

    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()
    events = res.json()  # [{"Date": "...", "Time": "...", "FaceLostDurationSec": ...}, ...]

    # 저장
    created_count = 0
    for item in events:
        FaceLostEvent.objects.create(
            user=user,
            date=item['Date'],
            time=item['Time'],
            duration_sec=item['FaceLostDurationSec']
        )
        created_count += 1

    return created_count

# focus/services.py (기존 코드 아래에 추가)

def calc_focus_score(blink_count, eyes_closed_time, zoning_out_time, present_ratio, heart_rate, total_duration_sec):
    score = 100 * present_ratio  # 출석률 반영한 시작점

    # 전체 측정 시간이 유효한 경우만 비율 감점
    if total_duration_sec > 0:
        zoning_ratio = zoning_out_time / total_duration_sec
        eyes_closed_ratio = eyes_closed_time / total_duration_sec
    else:
        zoning_ratio = 0
        eyes_closed_ratio = 0

    # 비율 감점 (퍼센트가 아니라 최대 감점량에 비례)
    score -= zoning_ratio * 50  # 멍때림은 최대 50점 감점
    score -= eyes_closed_ratio * 30  # 눈감음은 최대 30점 감점

    if blink_count < 3 or blink_count > 8:
        score -= 10

    if heart_rate < 55 or heart_rate > 110:
        score -= 10

    return max(0, min(100, round(score, 1)))  # 소수점 1자리

# 알림 함수
# @shared_task
# def notify_face_lost(user_id):
#     """
#     1분 후 실행되어, 마지막 FocusData가 present=False라면
#     얼굴 인식 실패 알림 전송
#     """
#     latest = FocusData.objects.filter(user_id=user_id).order_by('-timestamp').first()
#     if latest and not latest.present:
#         user = User.objects.get(id=user_id)
#         send_mail(
#             '얼굴 인식 실패 알림',
#             '1분 이상 얼굴 인식이 실패되었습니다.',
#             'no-reply@yourdomain.com',
#             [user.email],
#             fail_silently=True,
#         )
#
#
# @shared_task
# def notify_zoneout(user_id):
#     """
#     1분 후 실행되어, 최근 1분 동안 멍때림 누적이 60초 이상이면
#     멍때림 알림 전송
#     """
#     now = timezone.now()
#     window_start = now - timedelta(seconds=60)
#     zone_total = (
#         FocusData.objects
#         .filter(user_id=user_id, timestamp__gte=window_start)
#         .aggregate(total=Sum('zoning_out_time'))
#         ['total'] or 0
#     )
#     if zone_total >= 60:
#         user = User.objects.get(id=user_id)
#         send_mail(
#             '멍때림 알림',
#             '1분 이상 멍때림이 감지되었습니다.',
#             'no-reply@yourdomain.com',
#             [user.email],
#             fail_silently=True,
#         )
#
# #알람관련
# def schedule_alerts_for_user(user_id, present=False, zoning_out=False):
#     """
#     upload_focus_data 뷰 내에서 호출하세요.
#     present=False 또는 zoning_out=True 조건이 처음 감지되면
#     60초 후 알림 예약(중복 방지)
#     """
#     if present is False:
#         flag = f'face_lost_pending_{user_id}'
#         if not cache.get(flag):
#             cache.set(flag, True, 60)
#             notify_face_lost.apply_async((user_id,), countdown=60)
#     else:
#         cache.delete(f'face_lost_pending_{user_id}')
#
#     if zoning_out:
#         flag2 = f'zoneout_pending_{user_id}'
#         if not cache.get(flag2):
#             cache.set(flag2, True, 60)
#             notify_zoneout.apply_async((user_id,), countdown=60)
#     else:
#         cache.delete(f'zoneout_pending_{user_id}')