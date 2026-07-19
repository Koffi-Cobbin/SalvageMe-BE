from rest_framework.routers import DefaultRouter

from .admin_views import AdminCategoryViewSet, AdminListingViewSet

router = DefaultRouter()
router.register("listings", AdminListingViewSet, basename="admin-listing")
router.register("categories", AdminCategoryViewSet, basename="admin-category")

urlpatterns = router.urls
