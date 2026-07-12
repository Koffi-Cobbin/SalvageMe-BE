from rest_framework.routers import DefaultRouter

from .views import DropOffPointViewSet

router = DefaultRouter()
router.register("dropoff-points", DropOffPointViewSet, basename="dropoff-point")

urlpatterns = router.urls
