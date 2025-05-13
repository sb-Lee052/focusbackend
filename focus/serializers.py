from rest_framework import serializers
from .models import RawData, FaceLostEvent#, Heartbeat
from .models import Heartbeat, PressureEvent

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
