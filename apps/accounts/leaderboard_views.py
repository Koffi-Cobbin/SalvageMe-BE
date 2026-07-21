from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from . import leaderboard_services
from .leaderboard_serializers import LeaderboardSerializer, MyLeaderboardRankSerializer


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
