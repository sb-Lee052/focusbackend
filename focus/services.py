# focus/services.py
import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from .models import FaceLostEvent

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


