from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import ImpactStatsSerializer


class ImpactStatsView(APIView):
    """GET /api/v1/stats/impact/ — public, cached aggregate stats."""

    serializer_class = ImpactStatsSerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        snapshot = services.get_cached_impact_stats()
        if snapshot is None:
            snapshot = services.recompute_impact_stats()
        return Response(ImpactStatsSerializer(snapshot).data)
