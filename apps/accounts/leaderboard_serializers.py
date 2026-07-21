from django.utils import timezone
from rest_framework import serializers

from .models import FeaturedDonor, User


class LeaderboardEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    username = serializers.CharField()
    avatar_url = serializers.URLField(allow_null=True)
    completed_donation_count = serializers.IntegerField()
    average_rating = serializers.FloatField(allow_null=True)
    hero_tier = serializers.CharField(allow_null=True)


class LeaderboardSerializer(serializers.Serializer):
    period = serializers.CharField()
    results = LeaderboardEntrySerializer(many=True)


class MyLeaderboardRankSerializer(serializers.Serializer):
    rank = serializers.IntegerField(allow_null=True)
    username = serializers.CharField()
    completed_donation_count = serializers.IntegerField()
    average_rating = serializers.FloatField(allow_null=True)
    hero_tier = serializers.CharField(allow_null=True)


class FeaturedDonorSerializer(serializers.Serializer):
    """Public shape — GET /leaderboard/featured/."""

    id = serializers.IntegerField()
    username = serializers.CharField(source="user.username")
    avatar_url = serializers.URLField(source="user.avatar_url", allow_null=True)
    blurb = serializers.CharField()
    featured_from = serializers.DateTimeField()
    featured_until = serializers.DateTimeField(allow_null=True)


class AdminFeaturedDonorSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = FeaturedDonor
        fields = ["id", "user", "username", "blurb", "featured_from", "featured_until", "created_by", "created_at"]
        read_only_fields = ["id", "username", "created_by", "created_at"]


class CreateFeaturedDonorSerializer(serializers.Serializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source="user")
    blurb = serializers.CharField(required=False, allow_blank=True, default="")
    featured_from = serializers.DateTimeField(required=False)
    featured_until = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        attrs.setdefault("featured_from", timezone.now())
        return attrs
