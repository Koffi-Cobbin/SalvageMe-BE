import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import FeaturedDonor

pytestmark = pytest.mark.django_db


class TestPublicFeaturedEndpoint:
    def test_no_auth_required(self, api_client):
        response = api_client.get(reverse("leaderboard-featured"))
        assert response.status_code == 200

    def test_returns_active_entries_with_blurb(self, api_client, user_factory):
        donor = user_factory(username="spotlighted")
        FeaturedDonor.objects.create(user=donor, blurb="Wonderful person!", featured_from=timezone.now())
        response = api_client.get(reverse("leaderboard-featured"))
        assert len(response.data) == 1
        assert response.data[0]["username"] == "spotlighted"
        assert response.data[0]["blurb"] == "Wonderful person!"

    def test_never_exposes_phone_or_email(self, api_client, user_factory):
        donor = user_factory(phone="+44 7000 000000")
        FeaturedDonor.objects.create(user=donor, featured_from=timezone.now())
        response = api_client.get(reverse("leaderboard-featured"))
        assert "phone" not in response.data[0]
        assert "email" not in response.data[0]


class TestAdminFeaturedDonorViewSet:
    def test_list_requires_capability(self, auth_client):
        client, user = auth_client(username="nofeat")
        response = client.get(reverse("admin-featured-donor-list"))
        assert response.status_code == 403

    def test_create_success(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["leaderboard.manage"])
        client, actor = auth_client(admin_role=role)
        donor = user_factory()
        response = client.post(
            reverse("admin-featured-donor-list"), {"user_id": donor.id, "blurb": "Great work!"}
        )
        assert response.status_code == 201
        assert FeaturedDonor.objects.filter(user=donor).exists()

    def test_create_rejects_opted_out_donor(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["leaderboard.manage"])
        client, actor = auth_client(admin_role=role)
        donor = user_factory(include_in_leaderboard=False)
        response = client.post(reverse("admin-featured-donor-list"), {"user_id": donor.id})
        assert response.status_code == 400

    def test_delete_success(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["leaderboard.manage"])
        client, actor = auth_client(admin_role=role)
        donor = user_factory()
        entry = FeaturedDonor.objects.create(user=donor, featured_from=timezone.now())
        response = client.delete(reverse("admin-featured-donor-detail", args=[entry.id]))
        assert response.status_code == 204
        assert not FeaturedDonor.objects.filter(pk=entry.pk).exists()

    def test_delete_requires_capability(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["dashboard.view"])  # unrelated capability
        client, actor = auth_client(admin_role=role)
        donor = user_factory()
        entry = FeaturedDonor.objects.create(user=donor, featured_from=timezone.now())
        response = client.delete(reverse("admin-featured-donor-detail", args=[entry.id]))
        assert response.status_code == 403
