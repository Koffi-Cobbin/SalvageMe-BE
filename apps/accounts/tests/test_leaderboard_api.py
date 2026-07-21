import pytest
from django.urls import reverse
from django.utils import timezone

from apps.exchanges.models import Exchange

pytestmark = pytest.mark.django_db


def complete_exchange(exchange_factory, **kwargs):
    exchange = exchange_factory(**kwargs)
    exchange.status = Exchange.Status.COMPLETED
    exchange.completed_at = timezone.now()
    exchange.save(update_fields=["status", "completed_at"])
    return exchange


class TestLeaderboardEndpoint:
    def test_public_no_auth_required(self, api_client):
        response = api_client.get(reverse("leaderboard"))
        assert response.status_code == 200
        assert response.data["period"] == "all_time"

    def test_returns_ranked_results(self, api_client, exchange_factory, listing_factory, user_factory):
        donor = user_factory(username="publicdonor")
        complete_exchange(exchange_factory, listing=listing_factory(owner=donor), donor=donor)

        response = api_client.get(reverse("leaderboard"))
        usernames = [r["username"] for r in response.data["results"]]
        assert "publicdonor" in usernames

    def test_period_query_param(self, api_client):
        response = api_client.get(reverse("leaderboard"), {"period": "this_month"})
        assert response.status_code == 200
        assert response.data["period"] == "this_month"

    def test_invalid_period_returns_400(self, api_client):
        response = api_client.get(reverse("leaderboard"), {"period": "nonsense"})
        assert response.status_code == 400

    def test_never_exposes_phone_or_email(self, api_client, exchange_factory, listing_factory, user_factory):
        donor = user_factory(username="privacycheck", phone="+44 7000 000000")
        complete_exchange(exchange_factory, listing=listing_factory(owner=donor), donor=donor)

        response = api_client.get(reverse("leaderboard"))
        entry = next(r for r in response.data["results"] if r["username"] == "privacycheck")
        assert "phone" not in entry
        assert "email" not in entry


class TestMyLeaderboardRankEndpoint:
    def test_requires_auth(self, api_client):
        response = api_client.get(reverse("leaderboard-me"))
        assert response.status_code == 401

    def test_no_donations_yet(self, auth_client):
        client, user = auth_client(username="newbie")
        response = client.get(reverse("leaderboard-me"))
        assert response.status_code == 200
        assert response.data["rank"] is None

    def test_with_donations(self, auth_client, exchange_factory, listing_factory):
        client, user = auth_client(username="activedon")
        complete_exchange(exchange_factory, listing=listing_factory(owner=user), donor=user)
        response = client.get(reverse("leaderboard-me"))
        assert response.data["rank"] == 1
        assert response.data["completed_donation_count"] == 1


class TestOptOutToggle:
    def test_user_can_opt_out_via_users_me(self, auth_client):
        client, user = auth_client(username="togglemyself")
        response = client.patch(reverse("user-me"), {"include_in_leaderboard": False})
        assert response.status_code == 200
        assert response.data["include_in_leaderboard"] is False
        user.refresh_from_db()
        assert user.include_in_leaderboard is False

    def test_admin_can_exclude_another_user_via_users_edit_capability(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.edit"])
        client, actor = auth_client(admin_role=role)
        target = user_factory()
        response = client.patch(reverse("admin-user-detail", args=[target.id]), {"include_in_leaderboard": False})
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.include_in_leaderboard is False
