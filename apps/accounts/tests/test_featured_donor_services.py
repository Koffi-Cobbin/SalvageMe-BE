import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts import leaderboard_services
from apps.accounts.models import FeaturedDonor

pytestmark = pytest.mark.django_db


class TestCreateFeaturedDonor:
    def test_success(self, user_factory):
        donor = user_factory()
        acting = user_factory()
        entry = leaderboard_services.create_featured_donor(
            user=donor, blurb="Amazing contributor!", featured_from=timezone.now(),
            featured_until=None, acting_user=acting,
        )
        assert entry.pk is not None
        assert entry.created_by_id == acting.id

    def test_rejects_opted_out_user(self, user_factory):
        donor = user_factory(include_in_leaderboard=False)
        acting = user_factory()
        with pytest.raises(ValidationError):
            leaderboard_services.create_featured_donor(
                user=donor, blurb="", featured_from=timezone.now(), featured_until=None, acting_user=acting,
            )


class TestGetActiveFeaturedDonors:
    def test_returns_currently_active_entry(self, user_factory):
        import datetime

        donor = user_factory()
        FeaturedDonor.objects.create(
            user=donor, featured_from=timezone.now() - datetime.timedelta(days=1),
            featured_until=timezone.now() + datetime.timedelta(days=1),
        )
        active = list(leaderboard_services.get_active_featured_donors())
        assert len(active) == 1
        assert active[0].user_id == donor.id

    def test_excludes_expired_entry(self, user_factory):
        import datetime

        donor = user_factory()
        FeaturedDonor.objects.create(
            user=donor, featured_from=timezone.now() - datetime.timedelta(days=10),
            featured_until=timezone.now() - datetime.timedelta(days=1),
        )
        active = list(leaderboard_services.get_active_featured_donors())
        assert len(active) == 0

    def test_excludes_future_entry(self, user_factory):
        import datetime

        donor = user_factory()
        FeaturedDonor.objects.create(
            user=donor, featured_from=timezone.now() + datetime.timedelta(days=1), featured_until=None,
        )
        active = list(leaderboard_services.get_active_featured_donors())
        assert len(active) == 0

    def test_indefinite_entry_is_active(self, user_factory):
        import datetime

        donor = user_factory()
        FeaturedDonor.objects.create(
            user=donor, featured_from=timezone.now() - datetime.timedelta(days=1), featured_until=None,
        )
        active = list(leaderboard_services.get_active_featured_donors())
        assert len(active) == 1


class TestRemoveFeaturedDonor:
    def test_success(self, user_factory):
        donor = user_factory()
        acting = user_factory()
        entry = FeaturedDonor.objects.create(user=donor, featured_from=timezone.now())
        leaderboard_services.remove_featured_donor(entry=entry, acting_user=acting)
        assert not FeaturedDonor.objects.filter(pk=entry.pk).exists()
