from rest_framework import serializers

from apps.accounts.models import User

from .models import DropOffPoint


class DropOffManagerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()


class AdminDropOffPointSerializer(serializers.ModelSerializer):
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    managers = DropOffManagerSerializer(many=True, read_only=True)

    class Meta:
        model = DropOffPoint
        fields = ["id", "name", "address", "latitude", "longitude", "coordinator", "managers"]
        read_only_fields = ["id", "managers"]

    def get_latitude(self, obj) -> float | None:
        return obj.location.y if obj.location else None

    def get_longitude(self, obj) -> float | None:
        return obj.location.x if obj.location else None


class AdminDropOffPointWriteSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(write_only=True, required=False)
    longitude = serializers.FloatField(write_only=True, required=False)

    class Meta:
        model = DropOffPoint
        fields = ["name", "address", "coordinator", "latitude", "longitude"]

    def _pop_location(self, validated_data):
        from django.contrib.gis.geos import Point

        lat = validated_data.pop("latitude", None)
        lng = validated_data.pop("longitude", None)
        if lat is not None and lng is not None:
            return Point(lng, lat, srid=4326)
        return None

    def create(self, validated_data):
        location = self._pop_location(validated_data)
        if location is not None:
            validated_data["location"] = location
        return super().create(validated_data)

    def update(self, instance, validated_data):
        location = self._pop_location(validated_data)
        if location is not None:
            instance.location = location
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        return AdminDropOffPointSerializer(instance, context=self.context).data


class AssignManagersSerializer(serializers.Serializer):
    user_ids = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True)
