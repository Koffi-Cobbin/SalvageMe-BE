from django.urls import path
from rest_framework.routers import DefaultRouter

from .admin_views import (
    AdminCapabilityListView,
    AdminMeView,
    AdminRoleViewSet,
    AdminUserRatingViewSet,
    AdminUserViewSet,
)
from .leaderboard_views import AdminFeaturedDonorViewSet

router = DefaultRouter()
router.register("roles", AdminRoleViewSet, basename="admin-role")
router.register("users", AdminUserViewSet, basename="admin-user")
router.register("ratings", AdminUserRatingViewSet, basename="admin-rating")
router.register("leaderboard/featured", AdminFeaturedDonorViewSet, basename="admin-featured-donor")

urlpatterns = [
    path("me/", AdminMeView.as_view(), name="admin-me"),
    path("capabilities/", AdminCapabilityListView.as_view(), name="admin-capabilities"),
    *router.urls,
]
