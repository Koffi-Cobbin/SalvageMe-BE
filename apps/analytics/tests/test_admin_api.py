import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestAdminDashboard:
    def test_requires_capability(self, auth_client):
        client, user = auth_client(username="nodash")
        response = client.get(reverse("admin-dashboard"))
        assert response.status_code == 403

    def test_success(self, auth_client, admin_role_factory, report_factory, book_request_factory):
        role = admin_role_factory(capabilities=["dashboard.view"])
        client, user = auth_client(admin_role=role)
        report_factory()
        book_request_factory()
        response = client.get(reverse("admin-dashboard"))
        assert response.status_code == 200
        assert response.data["open_reports_count"] == 1
        assert response.data["pending_requests_count"] == 1


class TestAdminStatsHistory:
    def test_requires_capability(self, auth_client):
        client, user = auth_client(username="nostats")
        response = client.get(reverse("admin-stats-history-list"))
        assert response.status_code == 403

    def test_lists_snapshots(self, auth_client, admin_role_factory):
        from apps.analytics.services import recompute_impact_stats

        role = admin_role_factory(capabilities=["dashboard.view"])
        client, user = auth_client(admin_role=role)
        recompute_impact_stats()
        response = client.get(reverse("admin-stats-history-list"))
        assert response.status_code == 200
        assert len(response.data["results"]) == 1


class TestAdminStatsRecompute:
    def test_requires_capability(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["dashboard.view"])  # not stats.recompute
        client, user = auth_client(admin_role=role)
        response = client.post(reverse("admin-stats-recompute"))
        assert response.status_code == 403

    def test_success(self, auth_client, admin_role_factory, listing_factory):
        role = admin_role_factory(capabilities=["stats.recompute"])
        client, user = auth_client(admin_role=role)
        listing_factory.create_batch(2)
        response = client.post(reverse("admin-stats-recompute"))
        assert response.status_code == 200
        assert response.data["total_listings"] == 2
