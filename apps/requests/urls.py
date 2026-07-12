from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BookRequestViewSet, ListingRequestCreateView

router = DefaultRouter()
router.register("requests", BookRequestViewSet, basename="request")

urlpatterns = [
    path(
        "listings/<int:listing_pk>/request/",
        ListingRequestCreateView.as_view({"post": "create"}),
        name="listing-request-create",
    ),
    *router.urls,
]
