from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ListingViewSet

router = DefaultRouter()
router.register("listings", ListingViewSet, basename="listing")
router.register("categories", CategoryViewSet, basename="category")

urlpatterns = router.urls
