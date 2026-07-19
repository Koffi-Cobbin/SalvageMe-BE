from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.permissions import HasAnyCapability

from .admin_serializers import (
    AdminDropOffPointSerializer,
    AdminDropOffPointWriteSerializer,
    AssignManagersSerializer,
)
from .models import DropOffPoint


class AdminDropOffPointViewSet(viewsets.ModelViewSet):
    """
    /api/v1/admin/dropoff-points/ — scoped to a user's assigned points
    unless they hold dropoff.manage_all. See docs/ADMIN_API_PLAN.md
    "Drop-off scoping: confirmed — Option B".
    """

    pagination_class = None
    permission_classes = [HasAnyCapability("dropoff.view", "dropoff.manage", "dropoff.manage_all")]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return AdminDropOffPointWriteSerializer
        return AdminDropOffPointSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DropOffPoint.objects.none()
        user = self.request.user
        queryset = DropOffPoint.objects.select_related("coordinator").prefetch_related("managers")
        if user.has_capability("dropoff.manage_all"):
            return queryset
        return queryset.filter(managers=user)

    def get_permissions(self):
        if self.action in ("create", "assign_managers"):
            return [HasAnyCapability("dropoff.manage_all")]
        if self.action in ("update", "partial_update", "destroy"):
            return [HasAnyCapability("dropoff.manage", "dropoff.manage_all")]
        # list/retrieve: dropoff.view (or either manage capability, which
        # implies being able to at least see what you manage).
        return [HasAnyCapability("dropoff.view", "dropoff.manage", "dropoff.manage_all")]

    def perform_create(self, serializer):
        # A brand-new point has no managers yet — creation requires the
        # unscoped capability (enforced above), so no auto-assignment
        # footgun here. See the plan doc's note on this deliberate choice.
        serializer.save()

    @action(detail=True, methods=["post"], url_path="assign-managers")
    def assign_managers(self, request, pk=None):
        point = self.get_object()
        serializer = AssignManagersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        point.managers.set(serializer.validated_data["user_ids"])

        from apps.moderation.services import record_audit_log

        record_audit_log(
            actor=request.user, action="dropoff_managers_assigned", target_type="dropoff_point", target_id=point.id,
            metadata={"manager_ids": [u.id for u in serializer.validated_data["user_ids"]]},
        )
        return Response(AdminDropOffPointSerializer(point).data)
