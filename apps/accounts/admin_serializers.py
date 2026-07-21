from rest_framework import serializers

from common.admin_capabilities import ALL_CAPABILITIES

from .models import AdminRole, User


class CapabilitySerializer(serializers.Serializer):
    code = serializers.CharField()
    description = serializers.CharField()


class AdminRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminRole
        fields = ["id", "name", "description", "capabilities", "is_protected", "created_at", "updated_at"]
        read_only_fields = ["id", "is_protected", "created_at", "updated_at"]

    def validate_capabilities(self, value):
        invalid = [c for c in value if c not in ALL_CAPABILITIES]
        if invalid:
            raise serializers.ValidationError(f"Unknown capability code(s): {invalid}")
        return value


class AdminRoleWriteSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=50)
    description = serializers.CharField(required=False, allow_blank=True)
    capabilities = serializers.ListField(child=serializers.CharField(), required=False)


class AssignRoleSerializer(serializers.Serializer):
    admin_role_id = serializers.PrimaryKeyRelatedField(
        queryset=AdminRole.objects.all(), allow_null=True, source="admin_role"
    )


class AdminMeSerializer(serializers.Serializer):
    """Response shape for GET /admin/me/ — deliberately not a ModelSerializer,
    since this is a computed view of the current user's admin access, not a
    direct model representation."""

    def to_representation(self, user):
        role = user.admin_role
        return {
            "admin_role": {"id": role.id, "name": role.name} if role else None,
            "capabilities": role.capabilities if role else [],
            "can_access_admin": role is not None,
        }


class AdminUserSerializer(serializers.ModelSerializer):
    admin_role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "phone", "role", "is_verified", "is_active",
            "include_in_leaderboard", "admin_role", "date_joined",
        ]
        read_only_fields = ["id", "username", "date_joined"]

    def get_admin_role(self, obj) -> dict | None:
        if not obj.admin_role:
            return None
        return {"id": obj.admin_role.id, "name": obj.admin_role.name}


class AdminUserEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["role", "phone", "is_verified", "include_in_leaderboard"]
