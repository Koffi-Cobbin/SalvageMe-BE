from rest_framework.routers import DefaultRouter

from .views import ExchangeViewSet

router = DefaultRouter()
router.register("exchanges", ExchangeViewSet, basename="exchange")

urlpatterns = router.urls
