from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from . import services
from .admin_serializers import AuditLogSerializer
from .models import AuditLog, Report
from .serializers import ReportSerializer


class AdminPagination(CursorSetPagination):
    ordering = "-created_at"


class AdminReportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Report.objects.select_related("reporter", "resolved_by").all()
    serializer_class = ReportSerializer
    permission_classes = [HasCapability("reports.view")]
    pagination_class = AdminPagination
    filterset_fields = ["status", "reason", "target_type"]

    @action(detail=True, methods=["post"], permission_classes=[HasCapability("reports.resolve")])
    def resolve(self, request, pk=None):
        report = self.get_object()
        report = services.resolve_report(report=report, acting_user=request.user, outcome=Report.Status.RESOLVED)
        return Response(ReportSerializer(report).data)

    @action(detail=True, methods=["post"], permission_classes=[HasCapability("reports.resolve")])
    def dismiss(self, request, pk=None):
        report = self.get_object()
        report = services.resolve_report(report=report, acting_user=request.user, outcome=Report.Status.DISMISSED)
        return Response(ReportSerializer(report).data)


class AdminAuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = AuditLog.objects.select_related("actor").all()
    serializer_class = AuditLogSerializer
    permission_classes = [HasCapability("auditlog.view")]
    pagination_class = AdminPagination
    filterset_fields = ["action", "target_type"]
