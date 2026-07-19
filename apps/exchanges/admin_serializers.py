from rest_framework import serializers


class ForceOverrideSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)
