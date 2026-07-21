from django.urls import path

from .leaderboard_views import FeaturedDonorListView, LeaderboardView, MyLeaderboardRankView

urlpatterns = [
    path("leaderboard/me/", MyLeaderboardRankView.as_view(), name="leaderboard-me"),
    path("leaderboard/featured/", FeaturedDonorListView.as_view(), name="leaderboard-featured"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
]
