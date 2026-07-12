from rest_framework import serializers

from apps.accounts.serializers import PublicUserSerializer

from .models import BookRequest


class BookRequestSerializer(serializers.ModelSerializer):
    requester = PublicUserSerializer(read_only=True)
    listing_title = serializers.CharField(source="listing.title", read_only=True)

    class Meta:
        model = BookRequest
        fields = ["id", "listing", "listing_title", "requester", "status", "message", "created_at"]
        read_only_fields = ["id", "requester", "status", "created_at", "listing_title"]


class CreateBookRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookRequest
        fields = ["message"]
