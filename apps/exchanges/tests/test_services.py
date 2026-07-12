import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.exchanges import services
from apps.exchanges.models import Exchange
from apps.listings.models import Listing

pytestmark = pytest.mark.django_db


class TestScheduleExchange:
    def test_only_party_can_schedule(self, exchange_factory, user_factory):
        exchange = exchange_factory()
        stranger = user_factory(username="stranger")
        with pytest.raises(PermissionDenied):
            services.schedule_exchange(exchange=exchange, acting_user=stranger, scheduled_at=timezone.now())

    def test_donor_can_schedule(self, exchange_factory):
        exchange = exchange_factory()
        result = services.schedule_exchange(
            exchange=exchange, acting_user=exchange.donor, scheduled_at=timezone.now()
        )
        assert result.scheduled_at is not None


class TestCompleteExchange:
    def test_complete_marks_listing_claimed(self, exchange_factory):
        exchange = exchange_factory()
        result = services.complete_exchange(exchange=exchange, acting_user=exchange.recipient)
        assert result.status == Exchange.Status.COMPLETED
        exchange.listing.refresh_from_db()
        assert exchange.listing.status == Listing.Status.CLAIMED

    def test_complete_already_completed_rejected(self, exchange_factory):
        exchange = exchange_factory()
        services.complete_exchange(exchange=exchange, acting_user=exchange.donor)
        with pytest.raises(ValidationError):
            services.complete_exchange(exchange=exchange, acting_user=exchange.donor)

    def test_non_party_cannot_complete(self, exchange_factory, user_factory):
        exchange = exchange_factory()
        stranger = user_factory(username="stranger2")
        with pytest.raises(PermissionDenied):
            services.complete_exchange(exchange=exchange, acting_user=stranger)


class TestCancelExchange:
    def test_cancel_reverts_listing_to_available(self, exchange_factory):
        exchange = exchange_factory()
        exchange.listing.mark_pending()
        services.cancel_exchange(exchange=exchange, acting_user=exchange.donor)
        exchange.listing.refresh_from_db()
        assert exchange.listing.status == Listing.Status.AVAILABLE

    def test_cannot_cancel_completed_exchange(self, exchange_factory):
        exchange = exchange_factory()
        services.complete_exchange(exchange=exchange, acting_user=exchange.donor)
        with pytest.raises(ValidationError):
            services.cancel_exchange(exchange=exchange, acting_user=exchange.donor)


class TestRateExchange:
    def test_cannot_rate_before_completion(self, exchange_factory):
        exchange = exchange_factory()
        with pytest.raises(ValidationError):
            services.rate_exchange(exchange=exchange, acting_user=exchange.donor, score=5)

    def test_rate_success_after_completion(self, exchange_factory):
        exchange = exchange_factory()
        services.complete_exchange(exchange=exchange, acting_user=exchange.donor)
        rating = services.rate_exchange(exchange=exchange, acting_user=exchange.donor, score=5, comment="Great!")
        assert rating.rated_user_id == exchange.recipient_id
        assert rating.rated_by_id == exchange.donor_id

    def test_cannot_rate_twice(self, exchange_factory):
        exchange = exchange_factory()
        services.complete_exchange(exchange=exchange, acting_user=exchange.donor)
        services.rate_exchange(exchange=exchange, acting_user=exchange.donor, score=5)
        with pytest.raises(ValidationError):
            services.rate_exchange(exchange=exchange, acting_user=exchange.donor, score=4)

    def test_non_party_cannot_rate(self, exchange_factory, user_factory):
        exchange = exchange_factory()
        services.complete_exchange(exchange=exchange, acting_user=exchange.donor)
        stranger = user_factory(username="stranger3")
        with pytest.raises(PermissionDenied):
            services.rate_exchange(exchange=exchange, acting_user=stranger, score=5)


class TestSendExchangeReminders:
    def test_sends_reminders_for_upcoming_exchanges_in_window(self, exchange_factory, mailoutbox):
        exchange_factory(scheduled_at=timezone.now() + timezone.timedelta(hours=5))
        exchange_factory(scheduled_at=timezone.now() + timezone.timedelta(days=10))

        count = services.send_exchange_reminders(window_hours=24)

        assert count == 1
