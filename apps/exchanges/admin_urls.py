from rest_framework.routers import DefaultRouter

from .admin_views import AdminExchangeViewSet

router = DefaultRouter()
router.register("exchanges", AdminExchangeViewSet, basename="admin-exchange")

urlpatterns = router.urls
