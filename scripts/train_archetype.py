import os
import pickle

import numpy as np
import django
django.setup()

from django.conf import settings
from focus.ml import extract_user_features
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

def gather_all_features(days=7):
    """
    모든 활성 사용자(user) 혹은 특정 그룹의 user를 순회하며
    extract_user_features로부터 벡터를 모아서 하나의 큰 배열로 반환.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    features = []
    for user in User.objects.filter(is_active=True):
        vec = extract_user_features(user, days=days).flatten()
        features.append(vec)
    return np.vstack(features)

def find_best_k(X, max_k=8):
    from sklearn.metrics import silhouette_score
    import numpy as np

    n_samples = X.shape[0]
    # k는 2부터 min(max_k, n_samples - 1) 까지만 시도
    upper = min(max_k, n_samples - 1)
    best_k, best_score = None, -1

    for k in range(2, upper + 1):
        km = KMeans(n_clusters=k, random_state=42)
        labels = km.fit_predict(X)
        unique_labels = np.unique(labels)
        if len(unique_labels) < 2:
            print(f"K={k}, only one cluster found; skipping silhouette")
            continue
        score = silhouette_score(X, labels)
        print(f"K={k}, silhouette={score:.3f}")
        if score > best_score:
            best_k, best_score = k, score

    if best_k is None:
        # 유효한 k를 찾지 못했으면 기본값 설정
        best_k = 2 if n_samples >= 2 else 1
        print(f"No valid k found; defaulting best_k={best_k}")

    return best_k


def main():
    # 1) 데이터 준비
    X = gather_all_features(days=7)
    # 2) 최적 k 찾기 (엘보우나 실루엣)
    best_k = find_best_k(X)
    print("Best K =", best_k)

    # 3) 최종 모델 학습
    kmeans = KMeans(n_clusters=best_k, random_state=42)
    kmeans.fit(X)

    # 4) 모델 저장
    model_dir = settings.BASE_DIR / 'focus' / 'models'
    os.makedirs(model_dir, exist_ok=True)
    model_path = model_dir / 'kmeans_archetype.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(kmeans, f)
    print("Saved model to", model_path)

if __name__ == "__main__":
    main()