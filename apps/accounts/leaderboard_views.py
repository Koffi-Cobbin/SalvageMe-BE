from rest_framework import mixins, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from common.pagination import CursorSetPagination
from common.permissions import HasCapability

from . import leaderboard_services
from .leaderboard_serializers import (
    AdminFeaturedDonorSerializer,
    CreateFeaturedDonorSerializer,
    FeaturedDonorSerializer,
    LeaderboardSerializer,
    MyLeaderboardRankSerializer,
)
from .models import FeaturedDonor


class LeaderboardView(APIView):
    """GET /leaderboard/ — public, top-N donors by completed donation count."""

    serializer_class = LeaderboardSerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        period = request.query_params.get("period", "all_time")
        limit = int(request.query_params.get("limit", 20))
        data = leaderboard_services.get_leaderboard(period=period, limit=limit)
        return Response(LeaderboardSerializer(data).data)


class MyLeaderboardRankView(APIView):
    """GET /leaderboard/me/ — your own rank, even outside the top N."""

    serializer_class = MyLeaderboardRankSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period = request.query_params.get("period", "all_time")
        data = leaderboard_services.get_my_leaderboard_rank(user=request.user, period=period)
        return Response(MyLeaderboardRankSerializer(data).data)


class FeaturedDonorListView(APIView):
    """GET /leaderboard/featured/ — public, currently-active spotlight entries."""

    serializer_class = FeaturedDonorSerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        entries = leaderboard_services.get_active_featured_donors()
        return Response(FeaturedDonorSerializer(entries, many=True).data)


class AdminFeaturedDonorViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """
    /api/v1/admin/leaderboard/featured/ — manage the editorial spotlight.
    Lists every entry (past/present/future), not just currently-active
    ones, since staff need to see/manage upcoming and expired entries too.
    """

    queryset = FeaturedDonor.objects.select_related("user", "created_by")
    permission_classes = [HasCapability("leaderboard.manage")]
    pagination_class = CursorSetPagination

    def get_serializer_class(self):
        if self.action == "create":
            return CreateFeaturedDonorSerializer
        return AdminFeaturedDonorSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = leaderboard_services.create_featured_donor(acting_user=request.user, **serializer.validated_data)
        return Response(AdminFeaturedDonorSerializer(entry).data, status=201)

    def destroy(self, request, *args, **kwargs):
        entry = self.get_object()
        leaderboard_services.remove_featured_donor(entry=entry, acting_user=request.user)
        return Response(status=204)
