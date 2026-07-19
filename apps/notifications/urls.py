from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet, UnreadNotificationCountView

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("notifications/unread-count/", UnreadNotificationCountView.as_view(), name="notification-unread-count"),
    *router.urls,
]
