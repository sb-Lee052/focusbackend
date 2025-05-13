# focus/models.py
from django.db import models
from django.contrib.auth.models import User

class FocusData(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
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
    # heart_rate = models.IntegerField(
    #     default=75,
    #     help_text="심박수 (bpm)"
    # )

    def __str__(self):
        return f"FocusData {self.timestamp}"

class RawData(models.Model):
    focus_value     = models.FloatField(
        help_text="집중도 값 (0.0 ~ 1.0)",
        default=0.0
    )
    timestamp       = models.DateTimeField()
    blink_count     = models.IntegerField(
        help_text="눈 깜빡임 횟수",
        default=0
    )
    eyes_closed_time= models.FloatField(
        help_text="눈 감고 있는 시간(초)",
        default=0.0
    )
    zoning_out_time = models.FloatField(
        help_text="멍 때린 시간(초)",
        default=0.0
    )
    present = models.BooleanField(
        default=True,
        help_text="사용자가 자리에 있었는지 여부"
    )
    # heart_rate = models.IntegerField(
    #     default=75,
    #     help_text="심박수 (bpm)"
    # )

    def __str__(self):
        return f"{self.focus_value} @ {self.timestamp}"

class FaceLostEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()                   # "2025-05-02"
    time = models.TimeField()                   # "14:23"
    duration_sec = models.FloatField()          # 초단위 지속 시간


    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.date} {self.time} ({self.duration_sec}s)"


# 심박수 저장 모델
class Heartbeat(models.Model):
    timestamp = models.DateTimeField()
    bpm = models.IntegerField(help_text="심박수 (beats per minute)")

    def __str__(self):
        return f"{self.timestamp} - {self.bpm} bpm"

# 펜 압력 저장 모델
class PressureEvent(models.Model):
    timestamp = models.DateTimeField()
    pressure_value = models.FloatField(help_text="입력 값 (0~10)")

    def __str__(self):
        return f"{self.timestamp} - {'Pressed' if self.pressure_value else 'Released'}"