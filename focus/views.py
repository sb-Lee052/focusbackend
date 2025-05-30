
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

from .models import RawData, FocusData, FaceLostEvent
from .serializers import RawDataSerializer
from .services import calc_focus_score

from .models import Heartbeat, PressureEvent

from django.views.decorators.csrf import csrf_exempt


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
        "session_id": session.id,
        "start_at": session.start_at.isoformat()
    })

@csrf_exempt
@api_view(['POST'])
def end_study(request):
    session_id = request.POST.get('session_id') or request.data.get('session_id')
    try:
        session = StudySession.objects.get(id=session_id, user=request.user)
        session.end_at = timezone.now()
        session.save()
        duration = (session.end_at - session.start_at).total_seconds()
        return JsonResponse({
            "session_id": session.id,
            "start_at": session.start_at.isoformat(),
            "end_at": session.end_at.isoformat(),
            "duration": duration
        })
    except StudySession.DoesNotExist:
        return JsonResponse({"error": "Invalid session_id"}, status=400)



# 1) RawData 조회용 ViewSet
class RawDataViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RawData.objects.order_by('timestamp')
    serializer_class = RawDataSerializer
    permission_classes = [IsAuthenticated]

    # def get_queryset(self):
    #     return self.request.user.raw_data.order_by('timestamp')


# 2) raw_data 업로드
@api_view(['POST'])
def upload_raw_data(request):
    created = 0
    for item in request.data or []:
        ts = item.get('timestamp')
        dt = parse_datetime(ts)
        if not dt:
            continue
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())

        RawData.objects.create(
            user=request.user,
            blink_count=item.get('blink_count', 0),
            eyes_closed_time=item.get('eyes_closed_time', 0.0),
            zoning_out_time=item.get('zoning_out_time', 0.0),
            present=item.get('present', True),
            heart_rate=item.get('heart_rate', 75),
        )
        created += 1

    return Response({"message": f"{created} raw records saved."}, status=status.HTTP_201_CREATED)


# 3) focus_data 업로드
@api_view(['POST'])
def upload_focus_data(request):
    data = request.data or {}

    FocusData.objects.create(
        user=request.user,
        blink_count=data.get('blink_count', 0),
        eyes_closed_time=data.get('eyes_closed_time', 0.0),
        zoning_out_time=data.get('zoning_out_time', 0.0),
        present=data.get('present', True),
    )

    return Response({"message": "1 focus record saved."}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def upload_pressure_event(request):
    data = request.data
    timestamp = data.get('timestamp')
    is_pressed = data.get('is_pressed')

    if not timestamp or is_pressed is None:
        return Response({"error": "timestamp and is_pressed are required"}, status=400)

    PressureEvent.objects.create(timestamp=timestamp, is_pressed=is_pressed)
    return Response({"message": "pressure event saved"}, status=201)


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

    qs = RawData.objects.filter(timestamp__date=date_obj)
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
    return Response({'date': date_str, 'hourly_stats': list(hourly)})


# 5) 하루 전체 집중도 요약
@api_view(['GET'])
def get_focus_summary(request):
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Missing date'}, status=400)

    date = parse_date(date_str)
    start = datetime.combine(date, time.min)
    end = datetime.combine(date, time.max)

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

    return JsonResponse({
        "blink_count": blink_total,
        "eyes_closed_time_sec": int(eyes_closed),
        "zoneout_time_sec": int(zoneout),
        "focus_score": score,
        "study_time_min": int(total_duration_sec / 60),
        "present_ratio": present_ratio,
        "heart_rate": True
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
    qs = RawData.objects.filter(timestamp__range=(start, end))

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
            "absent": 10 if not item.present else 0,
            "zoneout": round(item.zoning_out_time, 2)
        })

    return JsonResponse({"timeline": timeline})


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

    # 1) time → datetime 파싱
    ts_str = data.get('time')
    if not ts_str:
        return Response({"error": "time 필드가 필요합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    dt = parse_datetime(ts_str)
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
    if hr is None:
        return Response({"error": "heart_rate 필드가 필요합니다."},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        bpm_value = int(round(float(hr)))
    except (TypeError, ValueError):
        return Response({"error": "heart_rate는 숫자여야 합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    # 4) pressure → is_pressed
    pres = data.get('pressure')
    if pres is None:
        return Response({"error": "pressure 필드가 필요합니다."},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        pressure_value = float(pres)

    except (TypeError, ValueError):
        return Response({"error": "pressure는 숫자여야 합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    # 5) 저장
    Heartbeat.objects.create(user=request.user, timestamp=dt, bpm=bpm_value)
    PressureEvent.objects.create(user=request.user, timestamp=dt, pressure_value=pressure_value)

    return Response({"message": "heartbeat 및 pressure 저장 완료"},
                    status=status.HTTP_201_CREATED)

class FocusDataViewSet(viewsets.ReadOnlyModelViewSet):
    """
    현재 로그인한 유저의 FocusData 목록 조회 (GET /focus/)
    """
    queryset = FocusData.objects.all()
    serializer_class = FocusDataSerializer
    permission_classes = [IsAuthenticated]
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['date', 'session']

    def get_queryset(self):
        # related_name='focus_data' 로 정의했으므로 아래와 같이도 가능
        return self.request.user.focus_data.order_by('-timestamp')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def all_summary_view(request):
    user = request.user
    data = FocusData.objects.filter(user=user).order_by('timestamp')

    summary_by_date = {}
    for item in data:
        date_str = item.timestamp.strftime('%Y-%m-%d')
        # 해당 날짜의 가장 마지막 focus_score만 저장
        summary_by_date[date_str] = item.focus_score

    result = [
        {"date": date, "focus_score": score}
        for date, score in summary_by_date.items()
    ]

    return Response(result)