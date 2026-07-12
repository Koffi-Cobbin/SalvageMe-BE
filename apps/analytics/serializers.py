from rest_framework import serializers

from .models import ImpactStatsSnapshot


class ImpactStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImpactStatsSnapshot
        fields = [
            "total_listings",
            "total_exchanges_completed",
            "total_active_donors",
            "total_active_recipients",
            "computed_at",
        ]
        read_only_fields = fields
