from django.urls import path
from rest_framework.routers import DefaultRouter

from .admin_views import AdminDashboardView, AdminStatsHistoryViewSet, AdminStatsRecomputeView

router = DefaultRouter()
router.register("stats/history", AdminStatsHistoryViewSet, basename="admin-stats-history")

urlpatterns = [
    path("dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("stats/recompute/", AdminStatsRecomputeView.as_view(), name="admin-stats-recompute"),
    *router.urls,
]
