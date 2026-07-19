from rest_framework import serializers


class DashboardSummarySerializer(serializers.Serializer):
    open_reports_count = serializers.IntegerField()
    pending_requests_count = serializers.IntegerField()
    unverified_users_count = serializers.IntegerField()
    listings_created_today = serializers.IntegerField()
    scheduled_exchanges_count = serializers.IntegerField()
