from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.auth_urls")),
    path("admin/", include("apps.accounts.admin_urls")),
    path("admin/", include("apps.listings.admin_urls")),
    path("admin/", include("apps.moderation.admin_urls")),
    path("admin/", include("apps.dropoff.admin_urls")),
    path("admin/", include("apps.exchanges.admin_urls")),
    path("admin/", include("apps.requests.admin_urls")),
    path("admin/", include("apps.analytics.admin_urls")),
    path("admin/", include("apps.partners.admin_urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.listings.urls")),
    path("", include("apps.requests.urls")),
    path("", include("apps.exchanges.urls")),
    path("", include("apps.dropoff.urls")),
    path("", include("apps.moderation.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.analytics.urls")),
    path("", include("apps.partners.urls")),
]
