from rest_framework.routers import DefaultRouter

from .admin_views import AdminDropOffPointViewSet

router = DefaultRouter()
router.register("dropoff-points", AdminDropOffPointViewSet, basename="admin-dropoff-point")

urlpatterns = router.urls
