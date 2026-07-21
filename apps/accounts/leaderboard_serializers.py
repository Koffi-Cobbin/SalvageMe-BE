from rest_framework import serializers


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
