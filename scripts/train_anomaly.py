import pickle
import numpy as np
import django; django.setup()

from django.contrib.auth import get_user_model
from focus.ml import get_window_features  # 10초 윈도우 피처 추출 함수
from focus.models import StudySession
from sklearn.svm import OneClassSVM

def main():
    User = get_user_model()

    # 1) 피처 행렬 수집
    X_list = []
    # 예: "정상"으로 간주할 최근 30일 종료된 세션
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=30)

    sessions = StudySession.objects.filter(
        end_at__isnull=False,
        end_at__gte=cutoff,
    )

    for sess in sessions:
        user = sess.user
        sess_id = sess.id
        # 해당 세션의 윈도우 피처 (shape = (T, feat_dim))
        windows = get_window_features(user, sess_id)
        if windows.size > 0:
            X_list.append(windows)

    if not X_list:
        print("학습할 윈도우 데이터가 없습니다. 조건을 확인하세요.")
        return

    # 2) numpy 배열로 합치기
    X = np.vstack(X_list)  # shape = (sum_T, feat_dim)

    # 3) One-Class SVM 모델 학습
    clf = OneClassSVM(kernel='rbf', nu=0.05, gamma='auto')
    clf.fit(X)

    # 4) 저장 (프로젝트 절대경로 기준)
    from django.conf import settings
    model_dir = settings.BASE_DIR / 'focus' / 'models'
    model_path = model_dir / 'anomaly_svm.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(clf, f)

    print(f"Saved One-Class SVM anomaly detector to {model_path}")

if __name__ == "__main__":
    main()