from rest_framework.routers import DefaultRouter

from .admin_views import AdminPartnerApplicationViewSet

router = DefaultRouter()
router.register("partner-applications", AdminPartnerApplicationViewSet, basename="admin-partner-application")

urlpatterns = router.urls
