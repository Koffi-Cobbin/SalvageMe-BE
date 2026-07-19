import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestAdminExchangeViewSet:
    def test_list_requires_capability(self, auth_client, exchange_factory):
        client, user = auth_client(username="noexview")
        response = client.get(reverse("admin-exchange-list"))
        assert response.status_code == 403

    def test_list_returns_all_exchanges(self, auth_client, admin_role_factory, exchange_factory):
        role = admin_role_factory(capabilities=["exchanges.view"])
        client, user = auth_client(admin_role=role)
        exchange_factory.create_batch(3)
        response = client.get(reverse("admin-exchange-list"))
        assert len(response.data["results"]) == 3

    def test_force_cancel_requires_capability(self, auth_client, admin_role_factory, exchange_factory):
        role = admin_role_factory(capabilities=["exchanges.view"])
        client, user = auth_client(admin_role=role)
        exchange = exchange_factory()
        response = client.post(
            reverse("admin-exchange-force-cancel", args=[exchange.id]), {"reason": "abandoned"}
        )
        assert response.status_code == 403

    def test_force_cancel_requires_reason(self, auth_client, admin_role_factory, exchange_factory):
        role = admin_role_factory(capabilities=["exchanges.force_override"])
        client, user = auth_client(admin_role=role)
        exchange = exchange_factory()
        response = client.post(reverse("admin-exchange-force-cancel", args=[exchange.id]), {})
        assert response.status_code == 400

    def test_force_cancel_success_by_non_party(self, auth_client, admin_role_factory, exchange_factory):
        role = admin_role_factory(capabilities=["exchanges.force_override"])
        client, staff = auth_client(admin_role=role)  # not donor or recipient
        exchange = exchange_factory()
        response = client.post(
            reverse("admin-exchange-force-cancel", args=[exchange.id]), {"reason": "abandoned by both parties"}
        )
        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        exchange.listing.refresh_from_db()
        assert exchange.listing.status == "available"

    def test_force_complete_success(self, auth_client, admin_role_factory, exchange_factory):
        role = admin_role_factory(capabilities=["exchanges.force_override"])
        client, staff = auth_client(admin_role=role)
        exchange = exchange_factory()
        response = client.post(
            reverse("admin-exchange-force-complete", args=[exchange.id]), {"reason": "confirmed via support ticket #42"}
        )
        assert response.status_code == 200
        assert response.data["status"] == "completed"
        exchange.listing.refresh_from_db()
        assert exchange.listing.status == "claimed"
