
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import FocusScoreAPIView
from .views import upload_heartbeat_data#, upload_pressure_data
from django.urls import path
from focus.views import start_study, end_study


router = DefaultRouter()
router.register(r'raw', views.RawDataViewSet, basename='raw')
router.register(r'focus', views.FocusDataViewSet, basename='focus')
urlpatterns = [
    # ViewSet 라우팅
    path('', include(router.urls)),

    # RawData 업로드
    path('upload/raw/',    views.upload_raw_data,           name='upload-raw-data'),
    # FocusData 업로드
    path('upload/',        views.upload_focus_data,         name='upload-focus-data'),

    # 심박+압력 통합 업로드
    path('upload/heartbeat/', upload_heartbeat_data,        name='upload-heartbeat'),

    # Date별 집중도
    path('data/',          views.focus_data_by_date,        name='focus-data-by-date'),
    # 전체 요약
    path('summary/',       views.get_focus_summary,         name='get-focus-summary'),
    # 일일 요약
    path('daily_summary/', views.daily_focus_summary,       name='daily-focus-summary'),
    # 얼굴 감지 손실 이벤트
    path('face_lost_summary/', views.upload_face_lost_summary, name='face-lost-summary'),

    # 점수 API
    path('score/',         FocusScoreAPIView.as_view(),     name='focus-score'),
    # 타임라인
    path('timeline/',      views.focus_timeline,            name='focus-timeline'),
    # 분 단위 깜빡임 요약
    path('blink_summary/', views.blink_summary_by_minute,   name='blink-summary'),
    # 공부 시작
    path('study-sessions/start/', start_study, name='start_study'),
    # 공부 종료
    path('study-sessions/end/',   end_study,   name='end_study'),

    path("all-summary/", views.all_summary_view),
]

