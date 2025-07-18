# scripts/train_explain.py
import pickle
import numpy as np
import django; django.setup()

from focus.ml import extract_session_features  # 세션 단위 피처
from focus.models import StudySession         # 예: label 저장 모델
from sklearn.ensemble import RandomForestRegressor

def main():
    # 1) 세션별 피처/라벨 데이터 모으기
    X, y = [], []
    for sess in StudySession.objects.exclude(success_score__isnull=True):
        feats = extract_session_features(sess.user, sess.id)
        X.append(feats)
        y.append(sess.success_score)  # 혹은 session_length

    X, y = np.vstack(X), np.array(y)

    # 2) 모델 학습
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 3) 저장
    with open('focus/models/explain_model.pkl','wb') as f:
        pickle.dump(model, f)

if __name__ == "__main__":
    main()