from rest_framework.routers import DefaultRouter

from .admin_views import AdminBookRequestViewSet

router = DefaultRouter()
router.register("requests", AdminBookRequestViewSet, basename="admin-request")

urlpatterns = router.urls
