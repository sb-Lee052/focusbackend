# focus/models.py

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings



class StudySession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.CASCADE,
        related_name = 'study_sessions'
        )
    place    = models.CharField(max_length=50)
    start_at = models.DateTimeField()
    end_at   = models.DateTimeField(null=True, blank=True)

    success_score = models.FloatField(
        null=True, blank=True,
        help_text="(예: 세션 성공도, 세션 길이, 별점 등)"
    )

    def __str__(self):
        return f"{self.user} @ {self.place} ({self.start_at} – {self.end_at})"


class FocusData(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.CASCADE,
        related_name = 'focus_data'
                            )
    score = models.IntegerField(default=0.0)
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, null=True, blank=True,
        related_name="focus_data")
    timestamp = models.DateTimeField()
    blink_count = models.IntegerField(
        default=0,
        help_text="깜빡임 횟수 (기존 레코드는 0으로 채움)"
    )
    eyes_closed_time = models.FloatField(
        default=0.0,
        help_text="눈 감고 있는 시간(초) (기존 레코드는 0.0으로 채움)"
    )
    zoning_out_time = models.FloatField(
        default=0.0,
        help_text="멍 때린 시간(초) (기존 레코드는 0.0으로 채움)"
    )
    present = models.BooleanField(
        default=True,
        help_text="사용자가 현재 자리에 있는지 여부"
    )
    focus_score = models.FloatField(default=0.0)
    # heart_rate = models.IntegerField(
    #     default=75,
    #     help_text="심박수 (bpm)"
    # )

    def __str__(self):
        return f"FocusData {self.timestamp}"

class FaceLostEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.CASCADE,
        related_name = 'face_lost_events'
                            )
    date = models.DateField()                   # "2025-05-02"
    time = models.TimeField()                   # "14:23"
    duration_sec = models.FloatField()          # 초단위 지속 시간


    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.date} {self.time} ({self.duration_sec}s)"

class SensorData(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sensor_data'
    )
    session = models.ForeignKey(
        'StudySession',
        on_delete=models.CASCADE,
        related_name='sensor_data'
    )
    timestamp     = models.DateTimeField()
    heart_rate    = models.IntegerField(
        null=True, blank=True,
        help_text="심박수 (beats per minute)"
    )
    pressure      = models.FloatField(
        null=True, blank=True,
        help_text="압력 값 (0~10)"
    )
    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.user} @ {self.timestamp}: HR={self.heart_rate}, P={self.pressure}"



