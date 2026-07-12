import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestListExchanges:
    def test_scoped_to_current_user(self, auth_client, exchange_factory):
        exchange = exchange_factory()
        client, _ = auth_client(user=exchange.donor)
        response = client.get(reverse("exchange-list"))
        assert response.status_code == 200
        ids = [e["id"] for e in response.data["results"]]
        assert exchange.id in ids

    def test_exposes_counterpart_contact_only_to_parties(self, auth_client, exchange_factory):
        exchange = exchange_factory()
        client, _ = auth_client(user=exchange.donor)
        response = client.get(reverse("exchange-detail", args=[exchange.id]))
        assert response.status_code == 200
        assert response.data["counterpart_contact"] is not None
        assert response.data["counterpart_contact"]["username"] == exchange.recipient.username

    def test_non_party_cannot_see_exchange(self, auth_client, exchange_factory):
        exchange = exchange_factory()
        client, _ = auth_client(username="outsider")
        response = client.get(reverse("exchange-detail", args=[exchange.id]))
        assert response.status_code == 404


class TestExchangeActions:
    def test_complete_by_party_success(self, auth_client, exchange_factory):
        exchange = exchange_factory()
        client, _ = auth_client(user=exchange.recipient)
        response = client.post(reverse("exchange-complete", args=[exchange.id]))
        assert response.status_code == 200
        assert response.data["status"] == "completed"

    def test_cancel_by_non_party_returns_404(self, auth_client, exchange_factory):
        exchange = exchange_factory()
        client, _ = auth_client(username="notparty")
        response = client.post(reverse("exchange-cancel", args=[exchange.id]))
        assert response.status_code == 404

    def test_rate_after_completion(self, auth_client, exchange_factory):
        exchange = exchange_factory()
        client, _ = auth_client(user=exchange.donor)
        client.post(reverse("exchange-complete", args=[exchange.id]))
        response = client.post(reverse("exchange-rate", args=[exchange.id]), {"score": 5, "comment": "Nice!"})
        assert response.status_code == 201

    def test_rate_invalid_score_rejected(self, auth_client, exchange_factory):
        exchange = exchange_factory()
        client, _ = auth_client(user=exchange.donor)
        client.post(reverse("exchange-complete", args=[exchange.id]))
        response = client.post(reverse("exchange-rate", args=[exchange.id]), {"score": 9})
        assert response.status_code == 400
