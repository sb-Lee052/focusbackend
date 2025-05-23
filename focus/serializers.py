from rest_framework import serializers
from .models import RawData, FaceLostEvent#, Heartbeat
from .models import Heartbeat, PressureEvent
from .models import FocusData
from .models import StudySession

class RawDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawData
        fields = '__all__'

class FaceLostEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaceLostEvent
        fields = ['date', 'time', 'duration_sec']

class HeartbeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Heartbeat
        fields = '__all__'

class PressureEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PressureEvent
        fields = '__all__'

class FocusDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = FocusData
        # user는 자동으로 request.user 로 채우고, timestamp는 읽기 전용으로 설정
        fields = ['id', 'blink_count', 'eyes_closed_time', 'zoning_out_time', 'present', 'timestamp']
        read_only_fields = ['id', 'timestamp']

class StudySessionSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = StudySession
        fields = ['id', 'user', 'start_at', 'end_at']
        read_only_fields = ['start_at', 'end_at']