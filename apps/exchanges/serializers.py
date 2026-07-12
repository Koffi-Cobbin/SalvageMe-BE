from rest_framework import serializers

from apps.accounts.serializers import PublicUserSerializer
from apps.dropoff.models import DropOffPoint
from apps.dropoff.serializers import DropOffPointSerializer

from .models import Exchange


class CounterpartContactSerializer(serializers.Serializer):
    """
    Precise contact info, only ever nested inside an ExchangeSerializer for
    a request made by one of the two matched parties (see
    SECURITY REQUIREMENTS: raw contact/location is never exposed publicly,
    only to the other matched party once a request is accepted).
    """

    username = serializers.CharField()
    phone = serializers.CharField(allow_null=True)
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    def get_latitude(self, obj) -> float | None:
        return obj.location.y if obj.location else None

    def get_longitude(self, obj) -> float | None:
        return obj.location.x if obj.location else None


class ExchangeSerializer(serializers.ModelSerializer):
    donor = PublicUserSerializer(read_only=True)
    recipient = PublicUserSerializer(read_only=True)
    dropoff_point = DropOffPointSerializer(read_only=True)
    counterpart_contact = serializers.SerializerMethodField()
    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = Exchange
        fields = [
            "id",
            "listing",
            "listing_title",
            "donor",
            "recipient",
            "dropoff_point",
            "status",
            "scheduled_at",
            "completed_at",
            "counterpart_contact",
        ]
        read_only_fields = fields

    def get_counterpart_contact(self, obj) -> dict | None:
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        if not obj.is_party(request.user):
            return None
        counterpart = obj.recipient if request.user.id == obj.donor_id else obj.donor
        return CounterpartContactSerializer(counterpart).data


class ScheduleExchangeSerializer(serializers.Serializer):
    scheduled_at = serializers.DateTimeField()
    dropoff_point = serializers.PrimaryKeyRelatedField(
        queryset=DropOffPoint.objects.all(), required=False, allow_null=True
    )


class RateExchangeSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
