"""
Synchronous notification sends, wired directly into the relevant service
functions/views (see ASYNC & SCHEDULED WORK: no Celery, no worker process
— PythonAnywhere free tier can't run one). Every send is wrapped so an
email provider hiccup never breaks the underlying API action: we log the
failure and move on rather than raising.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("salvageme")


def _send(*, subject: str, message: str, to_email: str | None) -> None:
    if not to_email:
        return
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
    except Exception:
        logger.exception("Notification email failed to send (subject=%r, to=%r)", subject, to_email)


def notify_request_received(book_request) -> None:
    owner = book_request.listing.owner
    _send(
        subject=f"New request for '{book_request.listing.title}'",
        message=(
            f"{book_request.requester.username} has requested your listing "
            f"'{book_request.listing.title}'. Log in to accept or decline."
        ),
        to_email=owner.email,
    )


def notify_request_accepted(book_request, exchange) -> None:
    _send(
        subject=f"Your request for '{book_request.listing.title}' was accepted",
        message=(
            f"Great news — your request was accepted. Coordinate the handoff "
            f"via exchange #{exchange.id}."
        ),
        to_email=book_request.requester.email,
    )


def notify_request_declined(book_request) -> None:
    _send(
        subject=f"Your request for '{book_request.listing.title}' was declined",
        message="The listing owner declined this request. Other listings may still be available.",
        to_email=book_request.requester.email,
    )


def notify_exchange_scheduled(exchange) -> None:
    for recipient in (exchange.donor, exchange.recipient):
        _send(
            subject=f"Exchange #{exchange.id} scheduled",
            message=f"Your exchange for '{exchange.listing.title}' is scheduled for {exchange.scheduled_at}.",
            to_email=recipient.email,
        )


def notify_exchange_completed(exchange) -> None:
    for recipient in (exchange.donor, exchange.recipient):
        _send(
            subject=f"Exchange #{exchange.id} completed — leave a rating",
            message=(
                f"Your exchange for '{exchange.listing.title}' is complete. "
                f"Please take a moment to rate the other party."
            ),
            to_email=recipient.email,
        )


def notify_exchange_reminder(exchange) -> None:
    for recipient in (exchange.donor, exchange.recipient):
        _send(
            subject=f"Reminder: exchange #{exchange.id} coming up",
            message=f"Your exchange for '{exchange.listing.title}' is scheduled for {exchange.scheduled_at}.",
            to_email=recipient.email,
        )
