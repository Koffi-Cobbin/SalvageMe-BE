from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from . import services
from .models import PartnerApplication
from .serializers import (
    ApprovePartnerApplicationSerializer,
    PartnerApplicationSerializer,
    RejectPartnerApplicationSerializer,
)


class AdminPartnerApplicationPagination(CursorSetPagination):
    ordering = "-created_at"


class AdminPartnerApplicationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PartnerApplication.objects.select_related("applicant_user", "reviewed_by")
    serializer_class = PartnerApplicationSerializer
    permission_classes = [HasCapability("partner_applications.review")]
    pagination_class = AdminPartnerApplicationPagination
    filterset_fields = ["status"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        application = self.get_object()
        serializer = ApprovePartnerApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = services.approve_partner_application(
            application=application, acting_user=request.user, **serializer.validated_data
        )
        return Response(PartnerApplicationSerializer(application).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        application = self.get_object()
        serializer = RejectPartnerApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = services.reject_partner_application(
            application=application, acting_user=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(PartnerApplicationSerializer(application).data)
