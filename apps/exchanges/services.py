from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import UserRating
from apps.notifications.services import notify_exchange_completed, notify_exchange_scheduled

from .models import Exchange


def _assert_is_party(exchange: Exchange, user) -> None:
    """
    Only the donor or recipient on this exchange may act on it — and only
    if they're still the correct parties tied to the listing (guards
    against a stale exchange row surviving a listing ownership edge case).
    """
    if not exchange.is_party(user):
        raise PermissionDenied("Only the donor or recipient on this exchange can perform this action.")
    if exchange.listing.owner_id != exchange.donor_id:
        raise ValidationError(
            {"detail": "This exchange's parties no longer match its listing.", "code": "stale_exchange"}
        )


def schedule_exchange(*, exchange: Exchange, acting_user, scheduled_at, dropoff_point=None) -> Exchange:
    _assert_is_party(exchange, acting_user)

    if exchange.status != Exchange.Status.SCHEDULED:
        raise ValidationError({"detail": f"Exchange is already {exchange.status}.", "code": "invalid_transition"})

    exchange.scheduled_at = scheduled_at
    if dropoff_point is not None:
        exchange.dropoff_point = dropoff_point
    exchange.save(update_fields=["scheduled_at", "dropoff_point"])

    notify_exchange_scheduled(exchange)
    return exchange


def complete_exchange(*, exchange: Exchange, acting_user) -> Exchange:
    _assert_is_party(exchange, acting_user)

    if exchange.status != Exchange.Status.SCHEDULED:
        raise ValidationError({"detail": f"Exchange is already {exchange.status}.", "code": "invalid_transition"})

    exchange.status = Exchange.Status.COMPLETED
    exchange.completed_at = timezone.now()
    exchange.save(update_fields=["status", "completed_at"])

    exchange.listing.mark_claimed()

    notify_exchange_completed(exchange)
    return exchange


def cancel_exchange(*, exchange: Exchange, acting_user) -> Exchange:
    _assert_is_party(exchange, acting_user)

    if exchange.status != Exchange.Status.SCHEDULED:
        raise ValidationError({"detail": f"Exchange is already {exchange.status}.", "code": "invalid_transition"})

    exchange.status = Exchange.Status.CANCELLED
    exchange.save(update_fields=["status"])

    exchange.listing.revert_to_available()
    return exchange


def rate_exchange(*, exchange: Exchange, acting_user, score: int, comment: str = "") -> UserRating:
    _assert_is_party(exchange, acting_user)

    if exchange.status != Exchange.Status.COMPLETED:
        raise ValidationError(
            {"detail": "You can only rate a completed exchange.", "code": "exchange_not_completed"}
        )

    already_rated = UserRating.objects.filter(exchange=exchange, rated_by=acting_user).exists()
    if already_rated:
        raise ValidationError(
            {"detail": "You have already rated this exchange.", "code": "duplicate_rating"}
        )

    rated_user = exchange.recipient if acting_user.id == exchange.donor_id else exchange.donor

    return UserRating.objects.create(
        exchange=exchange, rated_by=acting_user, rated_user=rated_user, score=score, comment=comment
    )


def send_exchange_reminders(*, window_hours: int) -> int:
    """
    Called by the daily `run_daily_jobs` management command. Sends a
    reminder for any scheduled exchange whose `scheduled_at` falls within
    the next `window_hours`. Because this only runs once a day on
    PythonAnywhere's free tier, this is a "falls within the next day's
    window" check rather than a precise "24h before" trigger — see
    ASYNC & SCHEDULED WORK for why finer granularity isn't attempted here.
    """
    from apps.notifications.services import notify_exchange_reminder

    now = timezone.now()
    window_end = now + timezone.timedelta(hours=window_hours)

    upcoming = Exchange.objects.filter(
        status=Exchange.Status.SCHEDULED, scheduled_at__gte=now, scheduled_at__lte=window_end
    )

    count = 0
    for exchange in upcoming.select_related("listing", "donor", "recipient"):
        notify_exchange_reminder(exchange)
        count += 1

    return count
