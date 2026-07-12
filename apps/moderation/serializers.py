from rest_framework import serializers

from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ["id", "target_type", "target_id", "reason", "detail", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]
