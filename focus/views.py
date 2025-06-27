import requests
from .models import StudySession
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from django.utils.timezone import make_naive, localtime, get_current_timezone
from datetime import datetime, time
from django.utils.dateparse import parse_datetime, parse_date
from django.utils import timezone
from django.db.models.functions import TruncHour
from django.db.models import Count, Sum
from .serializers import StudySessionSerializer, FocusDataSerializer, SensorDataSerializer

from rest_framework import viewsets, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse

from .models import FocusData, FaceLostEvent
from .services import calc_focus_score
from .models import SensorData
from django.views.decorators.csrf import csrf_exempt


def _get_current_session(user):
    # 아직 종료되지 않은 세션(2025-06-27 기준) 중 최신 세션을 반환
    return StudySession.objects.filter(user=user, end_at__isnull=True).first()

class StudySessionViewSet(viewsets.ModelViewSet):
    serializer_class = StudySessionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['start_at__date']

    def get_queryset(self):
        return StudySession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@csrf_exempt
@api_view(['POST'])
def start_study(request):
    place = request.data.get('place') or request.POST.get('place')
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
        return Response({"error": "활성화된 세션이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)
    session.end_at = timezone.now()
    session.save()
    return Response({"message": "세션이 종료되었습니다."}, status=status.HTTP_200_OK)


@api_view(['POST'])
def upload_focus_data(request):
    data = request.data or {}
    session = _get_current_session(request.user)
    if not session:
        return Response({"error": "먼저 /study-sessions/start/ 로 세션을 시작하세요."}, status=status.HTTP_400_BAD_REQUEST)

    ts = data.get('time')
    if not ts:
        return Response({"error": "time 필드가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
    dt = parse_datetime(ts)
    if not dt:
        return Response({"error": "time 형식이 유효하지 않습니다. ISO-8601 형식으로 보내주세요."}, status=status.HTTP_400_BAD_REQUEST)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    if not settings.USE_TZ:
        dt = make_naive(dt, timezone.get_current_timezone())

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
        focus_score=score
    )
    return Response({"message": "1 focus record saved."}, status=status.HTTP_201_CREATED)


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
        qs.annotate(hour=TruncHour('timestamp')).values('hour')
          .annotate(total_blinks=Sum('blink_count'), total_closed_time=Sum('eyes_closed_time'), total_zoning_time=Sum('zoning_out_time'), count=Count('id'))
          .order_by('hour')
    )
    return Response({'date': date_str, 'hourly_stats': list(hourly)})


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
        heart_rate=75,
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


@api_view(['GET'])
def daily_focus_summary(request):
    date_str = request.query_params.get('date')
    if not date_str:
        return JsonResponse({'error': 'date parameter required'}, status=400)
    date_obj = parse_date(date_str)
    start = datetime.combine(date_obj, time.min)
    end = datetime.combine(date_obj, time.max)
    qs = FocusData.objects.filter(timestamp__range=(start, end))
    total_count = qs.count()
    present_count = qs.filter(present=True).count()
    present_ratio = round(present_count / total_count, 2) if total_count else 0.0
    total_duration_sec = total_count * 10
    totals = qs.aggregate(blink_total=Sum('blink_count'), eyes_closed=Sum('eyes_closed_time'), zoneout_total=Sum('zoning_out_time'))
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


class FocusScoreAPIView(APIView):
    permission_classes = [IsAuthenticated]
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
        return Response({"focus_score": score, "flags": {"is_absent_or_zoning": is_absent_or_zoning, "is_drowsy": is_drowsy}})


@api_view(['GET'])
def focus_timeline(request):
    date_str = request.GET.get('date')
    if not date_str:
        return Response({'error': 'Missing date parameter (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)
    date = parse_date(date_str)
    if date is None:
        return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
    start = datetime.combine(date, time.min)
    end = datetime.combine(date, time.max)
    data = FocusData.objects.filter(timestamp__range=(start, end)).order_by('timestamp')
    timeline = []
    for item in data:
        ts_local = localtime(item.timestamp)
        timeline.append({
            "time": ts_local.strftime('%H:%M:%S'),
            "focus_score": round(item.focus_score or 0, 2),
            "absent": 10 if not item.present else 0,
            "zoneout": round(item.zoning_out_time, 2)
        })
    return JsonResponse({"timeline": timeline})


@api_view(['GET'])
def focus_score_data(request):
    user = request.user
    date_str = request.GET.get('date')
    if not date_str:
        return Response({'error': '날짜가 필요합니다.'}, status=400)
    focus_data = FocusData.objects.filter(user=user, timestamp__date=date_str).order_by('timestamp')
    timeline = []
    for rec in focus_data:
        ts = localtime(rec.timestamp)
        timeline.append({
            'time': ts.strftime('%H:%M:%S'),
            'score': round(rec.focus_score or 0, 2)
        })
    return Response({'timeline': timeline})
