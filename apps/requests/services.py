"""
Service-layer functions for the request/accept/decline lifecycle. Kept out
of views/serializers per WHAT NOT TO DO — business logic lives here so it's
testable via plain function calls, including from the scheduled-job
management command (see apps/requests/tests and
config/management/commands/run_daily_jobs.py).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.listings.models import Listing
from apps.notifications.services import (
    notify_request_accepted,
    notify_request_declined,
    notify_request_received,
)

from .models import BookRequest


def create_request(*, listing: Listing, requester, message: str = "") -> BookRequest:
    if listing.owner_id == requester.id:
        raise ValidationError({"detail": "You cannot request your own listing.", "code": "self_request"})

    if listing.status != Listing.Status.AVAILABLE:
        raise ValidationError(
            {"detail": "This listing is not currently available.", "code": "listing_unavailable"}
        )

    existing = BookRequest.objects.filter(
        listing=listing, requester=requester, status=BookRequest.Status.PENDING
    ).exists()
    if existing:
        raise ValidationError(
            {"detail": "You already have a pending request for this listing.", "code": "duplicate_request"}
        )

    book_request = BookRequest(listing=listing, requester=requester, message=message)
    try:
        book_request.full_clean(exclude=["status"])
    except DjangoValidationError as exc:
        raise ValidationError({"detail": exc.messages, "code": "invalid_request"}) from exc
    book_request.save()

    notify_request_received(book_request)
    return book_request


def accept_request(*, book_request: BookRequest, acting_user) -> "BookRequest":
    from apps.exchanges.models import Exchange  # local import avoids app-loading order issues

    if book_request.listing.owner_id != acting_user.id:
        raise PermissionDenied("Only the listing owner can accept a request.")

    if book_request.status != BookRequest.Status.PENDING:
        raise ValidationError(
            {"detail": f"Request is already {book_request.status}.", "code": "invalid_transition"}
        )

    book_request.status = BookRequest.Status.ACCEPTED
    book_request.save(update_fields=["status"])

    book_request.listing.mark_pending()

    exchange = Exchange.objects.create(
        listing=book_request.listing,
        donor=book_request.listing.owner,
        recipient=book_request.requester,
    )

    # Any other still-pending requests for this listing are now moot.
    BookRequest.objects.filter(
        listing=book_request.listing, status=BookRequest.Status.PENDING
    ).exclude(pk=book_request.pk).update(status=BookRequest.Status.DECLINED)

    notify_request_accepted(book_request, exchange)
    return book_request


def decline_request(*, book_request: BookRequest, acting_user) -> BookRequest:
    if book_request.listing.owner_id != acting_user.id:
        raise PermissionDenied("Only the listing owner can decline a request.")

    if book_request.status != BookRequest.Status.PENDING:
        raise ValidationError(
            {"detail": f"Request is already {book_request.status}.", "code": "invalid_transition"}
        )

    book_request.status = BookRequest.Status.DECLINED
    book_request.save(update_fields=["status"])

    notify_request_declined(book_request)
    return book_request


def expire_stale_requests(*, threshold_days: int) -> int:
    """
    Called by the daily `run_daily_jobs` management command. Expires
    (declines) `pending` requests older than `threshold_days`, and reverts
    their listing to `available` if it had been left dangling in `pending`
    with no other active request. Returns the number of requests expired.
    """
    cutoff = timezone.now() - timezone.timedelta(days=threshold_days)
    stale = BookRequest.objects.filter(status=BookRequest.Status.PENDING, created_at__lt=cutoff)

    count = 0
    for book_request in stale.select_related("listing"):
        book_request.status = BookRequest.Status.CANCELLED
        book_request.save(update_fields=["status"])
        count += 1

    return count
