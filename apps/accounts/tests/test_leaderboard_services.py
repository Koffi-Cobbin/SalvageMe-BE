import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts import leaderboard_services
from apps.exchanges.models import Exchange

pytestmark = pytest.mark.django_db


def complete_exchange(exchange_factory, **kwargs):
    exchange = exchange_factory(**kwargs)
    exchange.status = Exchange.Status.COMPLETED
    exchange.completed_at = timezone.now()
    exchange.save(update_fields=["status", "completed_at"])
    return exchange


class TestGetLeaderboard:
    def test_ranks_by_completed_donation_count(self, exchange_factory, listing_factory, user_factory):
        top_donor = user_factory(username="top")
        for _ in range(3):
            complete_exchange(exchange_factory, listing=listing_factory(owner=top_donor), donor=top_donor)

        low_donor = user_factory(username="low")
        complete_exchange(exchange_factory, listing=listing_factory(owner=low_donor), donor=low_donor)

        data = leaderboard_services.get_leaderboard(period="all_time", limit=20)
        usernames = [r["username"] for r in data["results"]]
        assert usernames.index("top") < usernames.index("low")
        assert data["results"][usernames.index("top")]["completed_donation_count"] == 3

    def test_excludes_non_completed_exchanges(self, exchange_factory, listing_factory, user_factory):
        donor = user_factory(username="scheduled_only")
        exchange_factory(listing=listing_factory(owner=donor), donor=donor)  # stays "scheduled"

        data = leaderboard_services.get_leaderboard(period="all_time", limit=20)
        usernames = [r["username"] for r in data["results"]]
        assert "scheduled_only" not in usernames

    def test_respects_opt_out(self, exchange_factory, listing_factory, user_factory):
        donor = user_factory(username="opted_out", include_in_leaderboard=False)
        complete_exchange(exchange_factory, listing=listing_factory(owner=donor), donor=donor)

        data = leaderboard_services.get_leaderboard(period="all_time", limit=20)
        usernames = [r["username"] for r in data["results"]]
        assert "opted_out" not in usernames

    def test_hero_tier_assigned_correctly(self, exchange_factory, listing_factory, user_factory):
        donor = user_factory(username="hero_test")
        for _ in range(5):
            complete_exchange(exchange_factory, listing=listing_factory(owner=donor), donor=donor)

        data = leaderboard_services.get_leaderboard(period="all_time", limit=20)
        entry = next(r for r in data["results"] if r["username"] == "hero_test")
        assert entry["hero_tier"] == "Hero"

    def test_average_rating_only_counts_ratings_as_donor(self, exchange_factory, listing_factory, user_factory, user_rating_factory):
        donor = user_factory(username="rated_donor")
        exchange = complete_exchange(exchange_factory, listing=listing_factory(owner=donor), donor=donor)
        # Rated as donor (this exchange's donor is this same user) — should count.
        user_rating_factory(rated_user=donor, exchange=exchange, score=5)

        # A second exchange where this same user is the *recipient*, rated well —
        # should NOT count toward their donor average.
        other_donor = user_factory(username="other_donor")
        exchange2 = complete_exchange(exchange_factory, listing=listing_factory(owner=other_donor), donor=other_donor, recipient=donor)
        user_rating_factory(rated_user=donor, exchange=exchange2, score=1)

        data = leaderboard_services.get_leaderboard(period="all_time", limit=20)
        entry = next(r for r in data["results"] if r["username"] == "rated_donor")
        assert entry["average_rating"] == 5.0

    def test_this_month_period_excludes_older_completions(self, exchange_factory, listing_factory, user_factory):
        import datetime

        donor = user_factory(username="old_completion")
        exchange = complete_exchange(exchange_factory, listing=listing_factory(owner=donor), donor=donor)
        Exchange.objects.filter(pk=exchange.pk).update(completed_at=timezone.now() - datetime.timedelta(days=90))

        data = leaderboard_services.get_leaderboard(period="this_month", limit=20)
        usernames = [r["username"] for r in data["results"]]
        assert "old_completion" not in usernames

        data_all = leaderboard_services.get_leaderboard(period="all_time", limit=20)
        usernames_all = [r["username"] for r in data_all["results"]]
        assert "old_completion" in usernames_all

    def test_invalid_period_rejected(self):
        with pytest.raises(ValidationError):
            leaderboard_services.get_leaderboard(period="last_decade")

    def test_limit_is_capped(self, exchange_factory, listing_factory, user_factory):
        for i in range(5):
            donor = user_factory(username=f"donor{i}")
            complete_exchange(exchange_factory, listing=listing_factory(owner=donor), donor=donor)
        data = leaderboard_services.get_leaderboard(period="all_time", limit=2)
        assert len(data["results"]) == 2


class TestGetMyLeaderboardRank:
    def test_zero_donations_returns_null_rank(self, user_factory):
        user = user_factory()
        result = leaderboard_services.get_my_leaderboard_rank(user=user, period="all_time")
        assert result["rank"] is None
        assert result["completed_donation_count"] == 0

    def test_rank_reflects_position_outside_top_n(self, exchange_factory, listing_factory, user_factory):
        for i in range(5):
            top_donor = user_factory(username=f"topper{i}")
            for _ in range(10 - i):
                complete_exchange(exchange_factory, listing=listing_factory(owner=top_donor), donor=top_donor)

        me = user_factory(username="me")
        complete_exchange(exchange_factory, listing=listing_factory(owner=me), donor=me)

        result = leaderboard_services.get_my_leaderboard_rank(user=me, period="all_time")
        assert result["rank"] == 6  # behind all 5 higher-count donors
