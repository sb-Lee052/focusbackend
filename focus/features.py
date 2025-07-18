# ──────────────────────────────────────────────────────────
# 윈도우 피쳐(10초단위), 세션피쳐(한세션 단위) 계산 추가
# ──────────────────────────────────────────────────────────

import numpy as np
from django.db.models import Avg, Sum, StdDev, Case, When, FloatField, Count
from django.db.models.functions import Trunc
from .models import FocusData, SensorData

def get_window_features(user, session_id, window_sec=10):
    # 1) FocusData 윈도우별 집계
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

    # 2) SensorData 윈도우별 집계 (필기 포함)
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

    # 3) 두 결과를 win(시간창) 기준으로 매핑
    fd_map = {row['win']: row for row in fd_qs}
    sd_map = {row['win']: row for row in sd_qs}

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
            wc,                # 필기 횟수
            wc / n             # 필기 비율
        ])

    return np.array(feats, dtype=float)

def extract_session_features(user, session_id):
    X = get_window_features(user, session_id)
    if X.size == 0:
        return np.zeros(9, dtype=float)

    total_focus       = X[:,0].sum()
    avg_blink         = X[:,1].mean()
    total_zoning      = X[:,3].sum()
    total_eyes_closed = X[:,2].sum()
    hr_var            = float(np.var(X[:,5]))
    pr_var            = float(np.var(X[:,6]))
    total_writing     = X[:,7].sum()          # 전체 필기 샘플 수
    avg_writing_ratio = float(X[:,8].mean())  # 윈도우당 평균 필기 비율

    return np.array([
        total_focus,
        avg_blink,
        total_zoning,
        total_eyes_closed,
        hr_var,
        pr_var,
        total_writing,
        avg_writing_ratio,
        X.shape[0]
    ], dtype=float)