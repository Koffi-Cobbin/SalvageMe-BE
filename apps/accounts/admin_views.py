from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.admin_capabilities import ALL_CAPABILITIES
from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from . import admin_services
from .admin_serializers import (
    AdminMeSerializer,
    AdminRoleSerializer,
    AdminRoleWriteSerializer,
    AdminUserEditSerializer,
    AdminUserSerializer,
    AssignRoleSerializer,
    CapabilitySerializer,
)
from .models import AdminRole, User, UserRating
from .serializers import UserRatingSerializer


class AdminPagination(CursorSetPagination):
    ordering = "-date_joined"


class AdminMeView(APIView):
    """GET /admin/me/ — any authenticated user, not gated by a capability.
    Lets the frontend decide whether to show admin navigation at all."""

    serializer_class = AdminMeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(AdminMeSerializer(request.user).data)


class AdminCapabilityListView(APIView):
    serializer_class = CapabilitySerializer
    permission_classes = [HasCapability("roles.manage")]

    def get(self, request):
        data = [{"code": code, "description": desc} for code, desc in ALL_CAPABILITIES.items()]
        return Response(data)


class AdminRoleViewSet(viewsets.ModelViewSet):
    queryset = AdminRole.objects.all()
    serializer_class = AdminRoleSerializer
    permission_classes = [HasCapability("roles.manage")]
    pagination_class = None

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return AdminRoleWriteSerializer
        return AdminRoleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = admin_services.create_admin_role(acting_user=request.user, **serializer.validated_data)
        return Response(AdminRoleSerializer(role).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        role = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        role = admin_services.update_admin_role(role=role, acting_user=request.user, **serializer.validated_data)
        return Response(AdminRoleSerializer(role).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        admin_services.delete_admin_role(role=role, acting_user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """
    /api/v1/admin/users/ — read/edit/suspend/reactivate/assign-role.
    Different actions require different capabilities (see get_permissions).
    Deliberately no create/destroy — accounts are created via /auth/register/
    (or the partner-application flow) and never deleted via the admin API.
    """

    queryset = User.objects.select_related("admin_role").all()
    pagination_class = AdminPagination
    filterset_fields = ["role", "is_verified", "is_active"]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return AdminUserEditSerializer
        return AdminUserSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [HasCapability("users.view")]
        if self.action in ("update", "partial_update"):
            return [HasCapability("users.edit")]
        if self.action in ("suspend", "reactivate"):
            return [HasCapability("users.suspend")]
        if self.action == "assign_role":
            return [HasCapability("roles.manage")]
        return [permissions.IsAdminUser]  # deny-by-default for anything unanticipated

    def perform_update(self, serializer):
        from apps.moderation.services import record_audit_log

        instance = serializer.instance
        before = {f: getattr(instance, f) for f in serializer.validated_data}
        serializer.save()
        after = {f: getattr(instance, f) for f in serializer.validated_data}
        diff = {f: {"old": before[f], "new": after[f]} for f in before if before[f] != after[f]}
        if diff:
            record_audit_log(
                actor=self.request.user, action="user_updated", target_type="user", target_id=instance.id,
                metadata=diff,
            )

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        user = self.get_object()
        if not user.is_active:
            raise ValidationError({"detail": "User is already suspended.", "code": "already_suspended"})
        user.is_active = False
        user.save(update_fields=["is_active"])
        from apps.moderation.services import record_audit_log

        record_audit_log(actor=request.user, action="user_suspended", target_type="user", target_id=user.id)
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        user = self.get_object()
        if user.is_active:
            raise ValidationError({"detail": "User is already active.", "code": "already_active"})
        user.is_active = True
        user.save(update_fields=["is_active"])
        from apps.moderation.services import record_audit_log

        record_audit_log(actor=request.user, action="user_reactivated", target_type="user", target_id=user.id)
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="assign-role")
    def assign_role(self, request, pk=None):
        user = self.get_object()
        serializer = AssignRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = admin_services.assign_admin_role(
            user=user, new_role=serializer.validated_data["admin_role"], acting_user=request.user
        )
        return Response(AdminUserSerializer(user).data)


class AdminRatingPagination(CursorSetPagination):
    ordering = "-created_at"


class AdminUserRatingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """/api/v1/admin/ratings/ — read-only, for trust & safety review."""

    queryset = UserRating.objects.select_related("rated_user", "rated_by", "exchange")
    serializer_class = UserRatingSerializer
    permission_classes = [HasCapability("ratings.view")]
    pagination_class = AdminRatingPagination
    filterset_fields = ["score"]
