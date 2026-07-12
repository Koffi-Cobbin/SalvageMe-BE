from django.urls import path

from .views import ImpactStatsView

urlpatterns = [
    path("stats/impact/", ImpactStatsView.as_view(), name="impact-stats"),
]
