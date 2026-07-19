from django.contrib.auth import password_validation
from django.contrib.gis.geos import Point
from rest_framework import serializers

from .models import User, UserRating


class PublicUserSerializer(serializers.ModelSerializer):
    """
    Safe-to-expose-publicly view of a user (e.g. as a listing's owner in
    search results). Never includes phone or precise location — see
    SECURITY REQUIREMENTS: raw location/contact info is only surfaced to
    the other matched party once a request is accepted (handled in the
    exchanges app's ExchangeContactSerializer, not here).
    """

    class Meta:
        model = User
        fields = ["id", "username", "role", "is_verified", "date_joined"]
        read_only_fields = fields


class UserMeSerializer(serializers.ModelSerializer):
    """Full self-view/edit for the authenticated user's own profile."""

    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "role",
            "phone",
            "is_verified",
            "avatar_url",
            "latitude",
            "longitude",
            "date_joined",
        ]
        read_only_fields = ["id", "username", "is_verified", "avatar_url", "date_joined"]

    def get_latitude(self, obj) -> float | None:
        return obj.location.y if obj.location else None

    def get_longitude(self, obj) -> float | None:
        return obj.location.x if obj.location else None

    def validate_role(self, value):
        if value not in User.Role.values:
            raise serializers.ValidationError("Invalid role.")
        return value

    def update(self, instance, validated_data):
        lat = self.initial_data.get("latitude")
        lng = self.initial_data.get("longitude")
        if lat is not None and lng is not None:
            instance.location = Point(float(lng), float(lat), srid=4326)
        return super().update(instance, validated_data)


class LoginRequestSerializer(serializers.Serializer):
    """Schema-only serializer for LoginView's request body (auth is handled by TokenObtainPairSerializer)."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class SetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        password_validation.validate_password(value)
        return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "role", "phone"]

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserRatingSerializer(serializers.ModelSerializer):
    rated_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = UserRating
        fields = ["id", "rated_user", "rated_by", "exchange", "score", "comment", "created_at"]
        read_only_fields = ["id", "rated_by", "created_at"]
