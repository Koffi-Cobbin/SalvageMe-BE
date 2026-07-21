from django.urls import path

from .leaderboard_views import LeaderboardView, MyLeaderboardRankView

urlpatterns = [
    path("leaderboard/me/", MyLeaderboardRankView.as_view(), name="leaderboard-me"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
]
