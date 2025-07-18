import numpy as np
from django.db.models import Avg, Sum, StdDev, Case, When, FloatField, Count
from django.db.models.functions import Trunc
from .models import FocusData, SensorData
from .constants import FEATURE_NAMES

def get_window_features(user, session_id, window_sec=10):
    # 1) FocusData 집계
    fd_qs = (
        FocusData.objects
        .filter(user=user, session_id=session_id)
        .annotate(win=Trunc('timestamp', f'{window_sec}s'))
        .values('win')
        .annotate(
            avg_focus=Avg('focus_score'),
            sum_blink=Sum('blink_count'),
            sum_eyes_closed=Sum('eyes_closed_time'),
            sum_zoning=Sum('zoning_out_time'),
            present_ratio=Avg(
                Case(When(present=True, then=1), default=0, output_field=FloatField())
            ),
            total_count=Count('id'),
        )
        .order_by('win')
    )

    # 2) SensorData 집계 (심박·압력·필기)
    sd_qs = (
        SensorData.objects
        .filter(user=user, session_id=session_id)
        .annotate(win=Trunc('timestamp', f'{window_sec}s'))
        .values('win')
        .annotate(
            hr_std=StdDev('heart_rate'),
            pressure_std=StdDev('pressure'),
            writing_count=Count(
                Case(When(pressure__gt=0, then=1), output_field=FloatField())
            )
        )
        .order_by('win')
    )

    # 3) 두 결과를 win 기준으로 합치기
    fd_map = {r['win']: r for r in fd_qs}
    sd_map = {r['win']: r for r in sd_qs}

    feats = []
    for win in sorted(set(fd_map) | set(sd_map)):
        f = fd_map.get(win, {})
        s = sd_map.get(win, {})
        n = f.get('total_count', 1)
        wc = s.get('writing_count', 0)
        feats.append([
            f.get('avg_focus', 0.0),
            f.get('sum_blink', 0),
            f.get('sum_eyes_closed', 0.0),
            f.get('sum_zoning', 0.0),
            f.get('present_ratio', 0.0),
            s.get('hr_std', 0.0),
            s.get('pressure_std', 0.0),
            wc,            # 필기 횟수
            wc / n         # 윈도우당 필기 비율
        ])

    return np.array(feats, dtype=float)


def extract_session_features(user, session_id):
    """
    한 세션(session_id)의 윈도우별 피처를 집계하여
    총 9개(FeatureNames와 일치)의 숫자 배열을 반환합니다.
    """
    X = get_window_features(user, session_id)  # shape = (T, 9)
    # 윈도우가 없으면 0 벡터 반환
    if X.size == 0:
        return np.zeros((len(FEATURE_NAMES),), dtype=float)

    total_focus       = float(X[:, 0].mean())            # 윈도우별 avg_focus 평균
    avg_blink         = float(X[:, 1].mean())            # 윈도우별 sum_blink 평균
    total_zoning      = float(X[:, 3].sum())             # 윈도우별 sum_zoning 합계
    total_eyes_closed = float(X[:, 2].sum())             # 윈도우별 sum_eyes_closed 합계
    hr_var            = float(np.nanvar(X[:, 5]))        # 윈도우별 hr_std 분산
    pr_var            = float(np.nanvar(X[:, 6]))        # 윈도우별 pressure_std 분산
    total_writing     = float(X[:, 7].sum())             # 윈도우별 writing_count 합계
    avg_writing_ratio = float(X[:, 8].mean())            # 윈도우당 글쓰기 비율 평균
    window_count      = float(X.shape[0])                # 윈도우 개수

    return np.array([
        total_focus,
        avg_blink,
        total_zoning,
        total_eyes_closed,
        hr_var,
        pr_var,
        total_writing,
        avg_writing_ratio,
        window_count
    ], dtype=float)