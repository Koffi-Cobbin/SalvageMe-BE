from django.contrib.gis.geos import Point
from rest_framework import serializers

from apps.accounts.serializers import PublicUserSerializer

from .models import Category, Listing, ListingPhoto


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class ListingPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingPhoto
        fields = ["id", "url", "order"]
        read_only_fields = fields


class ListingSerializer(serializers.ModelSerializer):
    """
    Read serializer. Deliberately omits precise lat/lng — public listing
    search only ever surfaces an approximate distance (see
    SECURITY REQUIREMENTS), computed by the view's geo annotation and
    exposed here as `distance_km` when present.
    """

    owner = PublicUserSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    images = ListingPhotoSerializer(many=True, read_only=True)
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            "id",
            "owner",
            "title",
            "description",
            "category",
            "grade_level",
            "condition",
            "status",
            "images",
            "distance_km",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_distance_km(self, obj) -> float | None:
        distance = getattr(obj, "distance", None)
        if distance is None:
            return None
        return round(distance.km, 2)


class ListingWriteSerializer(serializers.ModelSerializer):
    """
    Create/update serializer. `status` is intentionally not writable here —
    it is system-controlled via request-accept/exchange-completion flows
    (see WHAT NOT TO DO: a PATCH must never set status=claimed directly).
    """

    latitude = serializers.FloatField(write_only=True, required=False)
    longitude = serializers.FloatField(write_only=True, required=False)

    class Meta:
        model = Listing
        fields = [
            "id",
            "title",
            "description",
            "category",
            "grade_level",
            "condition",
            "latitude",
            "longitude",
        ]

    def _pop_location(self, validated_data):
        lat = validated_data.pop("latitude", None)
        lng = validated_data.pop("longitude", None)
        if lat is not None and lng is not None:
            return Point(lng, lat, srid=4326)
        return None

    def create(self, validated_data):
        location = self._pop_location(validated_data)
        validated_data["owner"] = self.context["request"].user
        if location is not None:
            validated_data["location"] = location
        return super().create(validated_data)

    def update(self, instance, validated_data):
        location = self._pop_location(validated_data)
        if location is not None:
            instance.location = location
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        # Return the same shape as reads after create/update so the
        # frontend gets consistent nested owner/category/images data.
        return ListingSerializer(instance, context=self.context).data
