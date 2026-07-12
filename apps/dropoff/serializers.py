from rest_framework import serializers

from .models import DropOffPoint


class DropOffPointSerializer(serializers.ModelSerializer):
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    class Meta:
        model = DropOffPoint
        fields = ["id", "name", "address", "latitude", "longitude"]
        read_only_fields = fields

    def get_latitude(self, obj) -> float | None:
        return obj.location.y if obj.location else None

    def get_longitude(self, obj) -> float | None:
        return obj.location.x if obj.location else None
