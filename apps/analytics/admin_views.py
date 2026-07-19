from rest_framework import mixins, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from . import services
from .admin_serializers import DashboardSummarySerializer
from .models import ImpactStatsSnapshot
from .serializers import ImpactStatsSerializer


class AdminDashboardView(APIView):
    serializer_class = DashboardSummarySerializer
    permission_classes = [HasCapability("dashboard.view")]

    def get(self, request):
        return Response(services.get_dashboard_summary())


class StatsHistoryPagination(CursorSetPagination):
    ordering = "-computed_at"


class AdminStatsHistoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ImpactStatsSnapshot.objects.all()
    serializer_class = ImpactStatsSerializer
    permission_classes = [HasCapability("dashboard.view")]
    pagination_class = StatsHistoryPagination


class AdminStatsRecomputeView(APIView):
    serializer_class = ImpactStatsSerializer
    permission_classes = [HasCapability("stats.recompute")]

    def post(self, request):
        snapshot = services.recompute_impact_stats()
        return Response(ImpactStatsSerializer(snapshot).data)
