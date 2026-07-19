from rest_framework import serializers

from apps.accounts.models import AdminRole

from .models import PartnerApplication


class SubmitPartnerApplicationSerializer(serializers.Serializer):
    applicant_name = serializers.CharField(max_length=200, required=False)
    applicant_email = serializers.EmailField(required=False)
    applicant_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    organization_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
    proposed_dropoff_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    proposed_dropoff_address = serializers.CharField(max_length=300, required=False, allow_blank=True)
    proposed_latitude = serializers.FloatField(required=False)
    proposed_longitude = serializers.FloatField(required=False)

    def validate(self, attrs):
        request = self.context.get("request")
        is_authenticated = request and request.user and request.user.is_authenticated
        if not is_authenticated:
            if not attrs.get("applicant_name"):
                raise serializers.ValidationError({"applicant_name": "This field is required."})
            if not attrs.get("applicant_email"):
                raise serializers.ValidationError({"applicant_email": "This field is required."})
        return attrs


class PartnerApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerApplication
        fields = [
            "id", "applicant_name", "applicant_email", "applicant_phone", "organization_name", "message",
            "proposed_dropoff_name", "proposed_dropoff_address", "email_verified_at", "status",
            "rejection_reason", "created_at",
        ]
        read_only_fields = fields


class ApprovePartnerApplicationSerializer(serializers.Serializer):
    admin_role_id = serializers.PrimaryKeyRelatedField(queryset=AdminRole.objects.all(), source="admin_role")
    assign_dropoff_manager = serializers.BooleanField(default=True, required=False)


class RejectPartnerApplicationSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)
