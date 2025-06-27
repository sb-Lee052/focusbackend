from rest_framework import serializers
from .models import FaceLostEvent#, Heartbeat
from .models import SensorData
from .models import FocusData
from .models import StudySession


class FaceLostEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaceLostEvent
        fields = ['date', 'time', 'duration_sec']

class SensorDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorData
        fields = [
            'id',
            'session',
            'timestamp',
            'heart_rate',
            'pressure',
        ]
        read_only_fields = ['id', 'session']

class FocusDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = FocusData
        # user는 자동으로 request.user 로 채우고, timestamp는 읽기 전용으로 설정
        fields = ['id', 'blink_count', 'eyes_closed_time', 'zoning_out_time', 'present', 'timestamp','session']
        read_only_fields = ['id','timestamp','session']

class StudySessionSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = StudySession
        fields = ['id', 'user', 'start_at', 'end_at']
        read_only_fields = ['start_at', 'end_at']