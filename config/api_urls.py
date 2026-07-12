from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.auth_urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.listings.urls")),
    path("", include("apps.requests.urls")),
    path("", include("apps.exchanges.urls")),
    path("", include("apps.dropoff.urls")),
    path("", include("apps.moderation.urls")),
    path("", include("apps.analytics.urls")),
]
