
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .ml import predict_archetype
from .ml import (
    predict_archetype,
    get_daily_recommendation,
    detect_anomalies,
    compute_shap
)
from django.db.models import Avg, Count
from django.views.decorators.cache import cache_page
from .serializers import StudySessionSerializer
from .models import StudySession
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import FocusDataSerializer
from django.conf import settings
from django.utils.timezone import make_naive
from datetime import datetime, time
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from django.db.models.functions import TruncHour
from django.db.models import Count, Sum

from rest_framework import viewsets, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse

from .models import FocusData, FaceLostEvent
from .services import calc_focus_score

from .models       import SensorData



from django.views.decorators.csrf import csrf_exempt

def _get_current_session(user):
    # 아직 종료(end_at=None)되지 않은 가장 최근의 세션 하나를 가져옵니다.
    return StudySession.objects.filter(user=user, end_at__isnull=True).first()

    # focus/views.py
class StudySessionViewSet(viewsets.ModelViewSet):
    serializer_class = StudySessionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['start_at__date']  # 모델 필드명이 start_time이라면 ['start_time__date']로 바꿔주세요

    def get_queryset(self):
        # 로그인 유저의 세션만 반환
        return StudySession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # user 필드를 클라이언트가 보내지 않아도 request.user로 자동 설정
        serializer.save(user=self.request.user)


@csrf_exempt
@api_view(['POST'])
def start_study(request):
    # 인증된 사용자(request.user) 가정
    place = request.POST.get('place') or request.data.get('place')
    session = StudySession.objects.create(
        user=request.user,
        place=place,
        start_at=timezone.now()
    )
    return JsonResponse({
        "session": session.id,
        "start_at": session.start_at.isoformat()
    })

@csrf_exempt
@api_view(['POST'])
def end_study(request):
    session = _get_current_session(request.user)
    if not session:
        return Response(
            {"error": "활성화된 세션이 없습니다."},
            status=status.HTTP_400_BAD_REQUEST
        )
    session.end_at = timezone.now()
    session.save()


    return Response({"message": "세션이 종료되었습니다."}, status=status.HTTP_200_OK)

# 3) focus_data 업로드
@api_view(['POST'])
def upload_focus_data(request):
    data = request.data or {}

    # 1) 클라이언트가 보낸 session ID 로 세션 조회 + 예외 처리
    session = _get_current_session(request.user)
    if not session:
        return Response(
        {"error": "먼저 /study-sessions/start/ 로 세션을 시작하세요."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2) 클라이언트가 보낸 time 파싱, 없으면 현재 시각 사용 (첫 번째 코드)
    # 1) time → datetime 파싱
    ts = data.get('time')
    if not ts:
        return Response({"error": "time 필드가 필요합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    dt = parse_datetime(ts)
    if not dt:
        return Response(
            {"error": "time 형식이 유효하지 않습니다. ISO-8601 형식으로 보내주세요."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2) timezone 처리
    # parse_datetime 로 받은 dt가 naive 라면 현재타임존으로 aware 처리
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    # MySQL + USE_TZ=False 환경에서는 반드시 naive datetime 으로 만들어야 함
    if not settings.USE_TZ:
        dt = make_naive(dt, timezone.get_current_timezone())

    # 3) FocusData 생성

    score = calc_focus_score(
        blink_count=data.get('blink_count', 0),
        eyes_closed_time=data.get('eyes_closed_time', 0.0),
        zoning_out_time=data.get('zoning_out_time', 0.0),
        present_ratio=1.0 if data.get('present', True) else 0.0,
        heart_rate=75,
        total_duration_sec=10
    )

    FocusData.objects.create(
        user=request.user,
        session=session,
        timestamp=dt,
        blink_count=data.get('blink_count', 0),
        eyes_closed_time=data.get('eyes_closed_time', 0.0),
        zoning_out_time=data.get('zoning_out_time', 0.0),
        present=data.get('present', True),
        focus_score=score  # ← 추가
    )


    return Response({"message": "1 focus record saved."}, status=status.HTTP_201_CREATED)


# @api_view(['POST'])
# def upload_pressure_event(request):
#     data = request.data
#     timestamp = data.get('timestamp')
#     is_pressed = data.get('is_pressed')
#
#     if not timestamp or is_pressed is None:
#         return Response({"error": "timestamp and is_pressed are required"}, status=400)
#
#     PressureEvent.objects.create(timestamp=timestamp, is_pressed=is_pressed)
#     return Response({"message": "pressure event saved"}, status=201)


# 4) 날짜별 시간대 집중도 집계
@api_view(['GET'])
def focus_data_by_date(request):
    date_str = request.query_params.get('date')
    if not date_str:
        return Response({'error': 'date parameter required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    qs = FocusData.objects.filter(timestamp__date=date_obj)
    hourly = (
        qs.annotate(hour=TruncHour('timestamp'))
          .values('hour')
          .annotate(
              total_blinks=Sum('blink_count'),
              total_closed_time=Sum('eyes_closed_time'),
              total_zoning_time=Sum('zoning_out_time'),
              count=Count('id'),
          )
          .order_by('hour')
    )
    return Response({'date': date_str,
                     'hourly_stats': list(hourly),
                     })


# 5) 하루 전체 집중도 요약
@api_view(['GET'])
def get_focus_summary(request):
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Missing date'}, status=400)

    date = parse_date(date_str)
    start = datetime.combine(date, time.min)
    end = datetime.combine(date, time.max)

    # 1) FocusData 집계
    data = FocusData.objects.filter(timestamp__range=(start, end))

    blink_total = data.aggregate(Sum('blink_count'))['blink_count__sum'] or 0
    eyes_closed = data.aggregate(Sum('eyes_closed_time'))['eyes_closed_time__sum'] or 0
    zoneout = data.aggregate(Sum('zoning_out_time'))['zoning_out_time__sum'] or 0

    total_count = data.count()
    total_duration_sec = total_count * 10 if total_count else 1

    present_count = data.filter(present=True).count()
    present_ratio = round(present_count / total_count, 2) if total_count else 0.0

    score = calc_focus_score(
        blink_count=blink_total,
        eyes_closed_time=eyes_closed,
        zoning_out_time=zoneout,
        present_ratio=present_ratio,
        heart_rate = 75,
        total_duration_sec=total_duration_sec
    )

    # 2) SensorData 집계 – 해당 날짜의 평균 심박수·압력
    sd_qs = SensorData.objects.filter(
        user=request.user,
        timestamp__range=(start, end)
    )
    avg_hr   = sd_qs.aggregate(Avg('heart_rate'))['heart_rate__avg'] or 0
    avg_pres = sd_qs.aggregate(Avg('pressure'))   ['pressure__avg']   or 0

    return JsonResponse({
        "blink_count": blink_total,
        "eyes_closed_time_sec": int(eyes_closed),
        "zoneout_time_sec": int(zoneout),
        "focus_score": score,
        "study_time_min": int(total_duration_sec / 60),
        "present_ratio": present_ratio,
        "heart_rate": round(avg_hr, 1),
        "pressure": round(avg_pres, 1),
    })


# 6) 간단한 일일 요약 (RawData 기준)
@api_view(['GET'])
def daily_focus_summary(request):
    date_str = request.query_params.get('date')
    if not date_str:
        return JsonResponse({'error': 'date parameter required'}, status=400)

    date_obj = parse_date(date_str)
    start = datetime.combine(date_obj, time.min)
    end = datetime.combine(date_obj, time.max)
    qs = FocusData.objects.filter(timestamp__date=(start, end))

    total_count = qs.count()
    present_count = qs.filter(present=True).count()
    present_ratio = round(present_count / total_count, 2) if total_count else 0.0
    total_duration_sec = total_count * 10

    totals = qs.aggregate(
        blink_total=Sum('blink_count'),
        eyes_closed=Sum('eyes_closed_time'),
        zoneout_total=Sum('zoning_out_time')
    )

    blink = totals.get('blink_total') or 0
    closed = totals.get('eyes_closed') or 0
    zoneout = totals.get('zoneout_total') or 0

    score = calc_focus_score(
        blink_count=blink,
        eyes_closed_time=closed,
        zoning_out_time=zoneout,
        present_ratio=present_ratio,
        heart_rate=75,
        total_duration_sec=total_duration_sec
    )

    return JsonResponse({
        'blink_count': blink,
        'eyes_closed_time_sec': int(closed),
        'zoneout_time_sec': int(zoneout),
        'focus_score': score,
        'study_time_min': int(total_duration_sec / 60),
        'present_ratio': present_ratio
    })


# 7) 얼굴 감지 안 된 이벤트 저장
@api_view(['POST'])
def upload_face_lost_summary(request):
    events = request.data or []
    created = 0
    for item in events:
        FaceLostEvent.objects.create(
            user=request.user,
            date=item.get('Date'),
            time=item.get('Time'),
            duration_sec=item.get('FaceLostDurationSec')
        )
        created += 1

    return Response({"message": f"{created} face-lost events saved."}, status=status.HTTP_201_CREATED)


# 8) 집중도 점수 + 경고 플래그
class FocusScoreAPIView(APIView):
    def post(self, request):
        data = request.data

        blink_count = data.get("blink_count", 0)
        eyes_closed_time = data.get("eyes_closed_time", 0)
        zoning_out_time = data.get("zoning_out_time", 0)
        present_ratio = data.get("present", 1)
        heart_rate = data.get("heart_rate", 75)
        total_duration_sec = data.get("total_duration_sec", 0)

        score = calc_focus_score(
            blink_count=blink_count,
            eyes_closed_time=eyes_closed_time,
            zoning_out_time=zoning_out_time,
            present_ratio=present_ratio,
            heart_rate=heart_rate,
            total_duration_sec=total_duration_sec
        )

        is_absent_or_zoning = (present_ratio < 0.1) or (zoning_out_time >= 20)
        is_drowsy = (eyes_closed_time >= 1) and (blink_count < 3) and (heart_rate < 60)

        return Response({
            "focus_score": score,
            "flags": {
                "is_absent_or_zoning": is_absent_or_zoning,
                "is_drowsy": is_drowsy
            }
        })


# 9) 시간별 집중 타임라인
@api_view(['GET'])
def focus_timeline(request):
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Missing date'}, status=400)

    date = parse_date(date_str)
    start = datetime.combine(date, time.min)
    end = datetime.combine(date, time.max)

    data = FocusData.objects.filter(timestamp__range=(start, end)).order_by('timestamp')

    timeline = []
    for item in data:
        timestamp = item.timestamp.strftime('%H:%M:%S')
        timeline.append({
            "time": timestamp,
            "focus_score": round(item.focus_score, 2),  # 추가
            "absent": 10 if not item.present else 0,
            "zoneout": round(item.zoning_out_time, 2)
        })

    return JsonResponse({"timeline": timeline})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sensor_timeline(request):
    """
    GET /focus/sensor-timeline/?date=YYYY-MM-DD
    Returns: {'timeline': [ {'time': 'HH:MM:SS', 'heart_rate': ..., 'pressure': ...}, ... ] }
    """
    date_str = request.query_params.get('date')
    if not date_str:
        return Response({'error': 'date parameter required'}, status=400)

    # YYYY-MM-DD 파싱
    d = parse_date(date_str)
    if not d:
        return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    # timestamp__date 필터로 해당 날짜의 모든 레코드 조회
    qs = SensorData.objects.filter(
        user=request.user,
        timestamp__date=d
    ).order_by('timestamp')

    # naive datetime 그대로 출력
    timeline = [
        {
            'time': s.timestamp.strftime('%H:%M:%S'),
            'heart_rate': s.heart_rate,
            'pressure':   s.pressure,
        }
        for s in qs
    ]

    return Response({'timeline': timeline})


# 10) 분 단위 깜빡임 요약
@api_view(['GET'])
def blink_summary_by_minute(request):
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Missing date'}, status=400)

    date = parse_date(date_str)
    start = datetime.combine(date, time.min)
    end = datetime.combine(date, time.max)

    data = FocusData.objects.filter(timestamp__range=(start, end)).order_by('timestamp')

    blink_map = {}
    for item in data:
        time_key = item.timestamp.replace(second=0, microsecond=0)
        if time_key not in blink_map:
            blink_map[time_key] = 0
        blink_map[time_key] += item.blink_count

    timeline = []
    for k in sorted(blink_map):
        count = blink_map[k]
        timeline.append({
            "time": k.strftime('%H:%M'),
            "blink_count": count,
            "drowsy": count <= 20
        })

    return JsonResponse({"timeline": timeline})

@csrf_exempt

@api_view(['POST'])
def upload_heartbeat_data(request):
    data = request.data

    # 1) 활성 세션 조회
    session = _get_current_session(request.user)
    if not session:
        return Response(
            {"error": "먼저 /study-sessions/start/ 로 세션을 시작하세요."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 1) time → datetime 파싱
    ts = data.get('time')
    if not ts:
        return Response({"error": "time 필드가 필요합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    dt = parse_datetime(ts)
    if not dt:
        return Response(
            {"error": "time 형식이 유효하지 않습니다. ISO-8601 형식으로 보내주세요."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2) timezone 처리
    # parse_datetime 로 받은 dt가 naive 라면 현재타임존으로 aware 처리
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    # MySQL + USE_TZ=False 환경에서는 반드시 naive datetime 으로 만들어야 함
    if not settings.USE_TZ:
        dt = make_naive(dt, timezone.get_current_timezone())

    # 3) heart_rate → bpm
    hr = data.get('heart_rate')
    pres = data.get('pressure')
    try:
        hr_val   = int(hr) if hr is not None else None
        pres_val = float(pres) if pres is not None else None
    except ValueError:
        return Response(
            {"error": "heart_rate와 pressure는 숫자여야 합니다."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 6) 레코드 생성 (session 자동 연결)
    SensorData.objects.create(
        user=request.user,
        session=session,  # ← 여기에 session 추가
        timestamp=dt,
        heart_rate=hr_val,
        pressure=pres_val
    )

    return Response({"message": "SensorData 저장 완료"},
                    status=status.HTTP_201_CREATED)

class FocusDataViewSet(viewsets.ReadOnlyModelViewSet):
    """
    현재 로그인한 유저의 FocusData 목록 조회 (GET /focus/)
    """
    queryset = FocusData.objects.all()
    serializer_class = FocusDataSerializer
    permission_classes = [IsAuthenticated]
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['session'] #date 제거함 : 모델에 없는 필드임으로 삭제

    def get_queryset(self):
        # related_name='focus_data' 로 정의했으므로 아래와 같이도 가능
        return self.request.user.focus_data.order_by('-timestamp')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def all_summary_view(request):
    data = FocusData.objects.filter(user=request.user).order_by('-timestamp')
    summary_by_date = {}
    for item in data:
        date_str = item.timestamp.strftime('%Y-%m-%d')
        summary_by_date.setdefault(date_str, item.focus_score)
    result = [
        {"date": date, "focus_score": score}
        for date, score in summary_by_date.items()
    ]
    return Response(result)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def focus_timeline_detail(request):
  # 1) date 파라미터가 있는지 확인
    date_str = request.GET.get('date')
    if not date_str:
        return Response(
            {'error': '날짜 파라미터(date)가 필요합니다. (YYYY-MM-DD 또는 ISO 형식)'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2) YYYY-MM-DD 형식 먼저 파싱
    date = parse_date(date_str)
    # 3) 실패하면 ISO-8601 전체 datetime 파싱 후 date 추출
    if date is None:
        dt = parse_datetime(date_str)
        if dt:
            date = dt.date()
    if date is None:
        return Response(
            {'error': '날짜 형식이 올바르지 않습니다. YYYY-MM-DD 또는 ISO 형식을 사용하세요.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    # 4) 이제 안전하게 combine 호출
    start = datetime.combine(date, time.min)
    end = datetime.combine(date, time.max)

    data = FocusData.objects.filter(
        user=request.user,
        timestamp__range=(start, end)
    ).order_by('timestamp')

    timeline = []
    for item in data:
        t = item.timestamp.strftime('%H:%M:%S')
        timeline.append({
            'time': t,
            'focus_score': round(item.focus_score, 2),
            'absent': 10 if not item.present else 0,
            'zoneout': round(item.zoning_out_time, 2)
        })

    return JsonResponse({"timeline": timeline})

@api_view(['GET'])
def focus_score_data(request):
    user = request.user
    date_str = request.GET.get('date')
    if not date_str:
        return Response({'error': '날짜가 필요합니다.'}, status=400)

    # 1) 문자열을 date 객체로 파싱
    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return Response({'error': '날짜 형식은 YYYY-MM-DD 이어야 합니다.'}, status=400)

    # 2) DB에서 date 필터
    focus_qs = FocusData.objects.filter(
        user=user,
        timestamp__date=query_date
    ).order_by('timestamp')

    # 3) 인스턴스 기준으로 로컬타임+문자열 포맷
    timeline = []
    for fd in focus_qs:
        local_ts = timezone.localtime(fd.timestamp)
        timeline.append({
            'time': local_ts.strftime('%H:%M:%S'),
            'focus_score': fd.focus_score
        })

    return Response({'timeline': timeline})



#집중점수 높은 시간대(시간단위) 5개 리턴하는 함수

@cache_page(60 * 5)  # 5분간 캐시
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def best_hours(request):
    user = request.user

    time_stats = (
        FocusData.objects
        .filter(user=user)
        .annotate(hour=TruncHour('timestamp'))
        .values('hour')
        .annotate(
            avg_score=Avg('focus_score'),
            count=Count('id')
        )
        .order_by('-avg_score')[:5]
    )

    result = [
        {
            'hour': item['hour'].strftime('%Y-%m-%d %H:%M:%S'),
            'avg_score': round(item['avg_score'], 2),
            'count': item['count'],
        }
        for item in time_stats
    ]

    return Response({'best_hours': result})


# 집중점수 높은 장소 리턴 함수

@cache_page(60 * 5)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def best_places(request):
    user = request.user

    # 상위 1개만 가져오도록 슬라이스를 1로 변경
    place_stats = (
        StudySession.objects
        .filter(user=user, focus_data__isnull=False)
        .values('place')
        .annotate(
            avg_score=Avg('focus_data__focus_score'),
            count=Count('focus_data')
        )
        .order_by('-avg_score')[:1]
    )

    if place_stats:
        item = place_stats[0]
        result = {
            'place': item['place'],
            'avg_score': round(item['avg_score'], 2),
            'count': item['count'],
        }
    else:
        result = {}

    return Response({'best_place': result})


# 집중유지시간 함수

THRESHOLD_SCORE = 60  # 디폴트 기준점수
INTERVAL_SEC = 10     # 데이터 간격(초)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_average_session_focus_duration(request):
    """
    GET /focus/concentration-summary/?threshold=<optional>
    - threshold: 점수 기준 (기본 60, >= 이면 집중 구간)
    Returns JSON with:
      * segments_count: 집중 구간 개수
      * max_focused_min: 최대 집중 지속시간(분)
      * min_focused_min: 최소 집중 지속시간(분)
      * average_focused_min: 평균 집중 지속시간(분)
      * threshold: 사용된 기준 점수
    """
    threshold = float(request.query_params.get('threshold', THRESHOLD_SCORE))

    qs = FocusData.objects.filter(user=request.user).order_by('timestamp')

    durations_sec = []
    count = 0
    for fd in qs:
        if fd.focus_score >= threshold:
            count += 1
        else:
            if count:
                durations_sec.append(count * INTERVAL_SEC)
                count = 0
    if count:
        durations_sec.append(count * INTERVAL_SEC)

    if durations_sec:
        max_sec = max(durations_sec)
        min_sec = min(durations_sec)
        avg_sec = sum(durations_sec) / len(durations_sec)
    else:
        max_sec = min_sec = avg_sec = 0

    max_min = round(max_sec / 60, 2)
    min_min = round(min_sec / 60, 2)
    avg_min = round(avg_sec / 60, 2)

    return Response({
        'segments_count': len(durations_sec),
        'max_focused_min': max_min,
        'min_focused_min': min_min,
        'average_focused_min': avg_min,
        'threshold': threshold,
    })

#머신러닝 추가
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def archetype_view(request):
    """
    GET /focus/archetype/
    현재 로그인 유저의 집중 아키타입 인덱스와 (선택)설명을 반환
    """
    idx = predict_archetype(request.user)
    # front에서 TYPE_INFO 매핑을 사용 중이니, 여기서는 인덱스만 내려줘도 충분합니다.
    return Response({
        "archetype": idx
    })

#학습+휴식 시간 추천
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def daily_schedule_view(request):
    rec = get_daily_recommendation(request.user, days=3)
    return Response(rec)

#이상치 예측
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def anomaly_view(request):
    session_id = request.query_params.get('session_id')
    if not session_id:
        return Response({'error': 'session_id 파라미터가 필요합니다.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        sid = int(session_id)
    except ValueError:
        return Response({'error': 'session_id는 정수여야 합니다.'},
                        status=status.HTTP_400_BAD_REQUEST)

    res = detect_anomalies(request.user, sid)
    return Response(res)

# SHAP/LIME 으로 피처 중요도 개인화
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def explain_view(request):
    session_id = request.GET.get('session_id')
    if not session_id:
        return Response({'error':'session_id required'}, status=400)
    res = compute_shap(request.user, session_id)
    return Response(res)