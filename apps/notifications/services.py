"""
Notification dispatch: creates a persisted Notification row AND (by default)
sends an email — two channels through one function, so every call site gets
an in-app record for free. Sends are synchronous, in the request cycle (see
ASYNC & SCHEDULED WORK in the README — no Celery, no worker process,
PythonAnywhere free tier can't run one). Every email send is wrapped so a
provider hiccup never breaks the underlying API action: log the failure and
move on rather than raising.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger("salvageme")


def _send_email(*, subject: str, message: str, to_email: str | None) -> None:
    if not to_email:
        return
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
    except Exception:
        logger.exception("Notification email failed to send (subject=%r, to=%r)", subject, to_email)


def notify(
    *,
    recipient,
    category: str,
    title: str,
    body: str = "",
    target_type: str = "",
    target_id: int | None = None,
    send_email: bool = True,
) -> Notification:
    """
    The single entry point for raising a notification anywhere in the app.
    Always creates a Notification row; sends an email too unless
    send_email=False. Every notify_* helper below is a thin wrapper around
    this — callers elsewhere in the codebase (apps/requests/services.py,
    apps/exchanges/services.py, etc.) keep calling those same helper names
    unchanged.
    """
    notification = Notification.objects.create(
        recipient=recipient,
        category=category,
        title=title,
        body=body,
        target_type=target_type,
        target_id=target_id,
    )
    if send_email:
        _send_email(subject=title, message=body, to_email=recipient.email)
    return notification


def notify_request_received(book_request) -> None:
    owner = book_request.listing.owner
    notify(
        recipient=owner,
        category=Notification.Category.REQUEST_RECEIVED,
        title=f"New request for '{book_request.listing.title}'",
        body=(
            f"{book_request.requester.username} has requested your listing "
            f"'{book_request.listing.title}'. Log in to accept or decline."
        ),
        target_type="request",
        target_id=book_request.id,
    )


def notify_request_accepted(book_request, exchange) -> None:
    notify(
        recipient=book_request.requester,
        category=Notification.Category.REQUEST_ACCEPTED,
        title=f"Your request for '{book_request.listing.title}' was accepted",
        body=(
            f"Great news — your request was accepted. Coordinate the handoff "
            f"via exchange #{exchange.id}."
        ),
        target_type="exchange",
        target_id=exchange.id,
    )


def notify_request_declined(book_request) -> None:
    notify(
        recipient=book_request.requester,
        category=Notification.Category.REQUEST_DECLINED,
        title=f"Your request for '{book_request.listing.title}' was declined",
        body="The listing owner declined this request. Other listings may still be available.",
        target_type="request",
        target_id=book_request.id,
    )


def notify_exchange_scheduled(exchange) -> None:
    for recipient in (exchange.donor, exchange.recipient):
        notify(
            recipient=recipient,
            category=Notification.Category.EXCHANGE_SCHEDULED,
            title=f"Exchange #{exchange.id} scheduled",
            body=f"Your exchange for '{exchange.listing.title}' is scheduled for {exchange.scheduled_at}.",
            target_type="exchange",
            target_id=exchange.id,
        )


def notify_exchange_completed(exchange) -> None:
    for recipient in (exchange.donor, exchange.recipient):
        notify(
            recipient=recipient,
            category=Notification.Category.EXCHANGE_COMPLETED,
            title=f"Exchange #{exchange.id} completed — leave a rating",
            body=(
                f"Your exchange for '{exchange.listing.title}' is complete. "
                f"Please take a moment to rate the other party."
            ),
            target_type="exchange",
            target_id=exchange.id,
        )


def notify_exchange_reminder(exchange) -> None:
    for recipient in (exchange.donor, exchange.recipient):
        notify(
            recipient=recipient,
            category=Notification.Category.EXCHANGE_REMINDER,
            title=f"Reminder: exchange #{exchange.id} coming up",
            body=f"Your exchange for '{exchange.listing.title}' is scheduled for {exchange.scheduled_at}.",
            target_type="exchange",
            target_id=exchange.id,
        )


def notify_report_resolved(report) -> None:
    """
    New — previously the reporter was never told the outcome of their own
    report. Called from apps/moderation/services.py::resolve_report.
    """
    outcome_text = "resolved" if report.status == "resolved" else "dismissed"
    notify(
        recipient=report.reporter,
        category=Notification.Category.REPORT_RESOLVED,
        title="Your report was reviewed",
        body=f"Your report ({report.get_reason_display()}) was {outcome_text}.",
        target_type="report",
        target_id=report.id,
    )


def notify_role_assigned(user, *, old_role_name: str | None, new_role_name: str | None) -> None:
    """
    New — lets a user know when their admin role changes, rather than
    silently discovering new (or missing) admin nav options.
    """
    if new_role_name:
        title = f"Your admin role is now '{new_role_name}'"
        body = f"Your admin access level changed from '{old_role_name or 'none'}' to '{new_role_name}'."
    else:
        title = "Your admin access was revoked"
        body = f"Your admin role ('{old_role_name}') was removed."
    notify(
        recipient=user,
        category=Notification.Category.ROLE_ASSIGNED,
        title=title,
        body=body,
        target_type="user",
        target_id=user.id,
    )


def notify_partner_application_ready(application) -> None:
    """
    Fires once an application's email is verified. Notifies every current
    holder of the partner_applications.review capability — see
    apps/partners/services.py, which guards this with
    application.reviewers_notified_at so it only ever fires once.
    """
    from apps.accounts.models import users_with_capability

    for reviewer in users_with_capability("partner_applications.review"):
        notify(
            recipient=reviewer,
            category=Notification.Category.PARTNER_APPLICATION_READY,
            title=f"New partner application: {application.applicant_name}",
            body=f"{application.applicant_name} applied to become a partner. Review it in the admin panel.",
            target_type="partner_application",
            target_id=application.id,
        )


def notify_partner_application_approved(application) -> None:
    notify(
        recipient=application.applicant_user,
        category=Notification.Category.PARTNER_APPLICATION_APPROVED,
        title="Your partner application was approved",
        body="Congratulations — your partner application has been approved.",
        target_type="partner_application",
        target_id=application.id,
    )


def notify_partner_application_rejected(application) -> None:
    notify(
        recipient=application.applicant_user,
        category=Notification.Category.PARTNER_APPLICATION_REJECTED,
        title="Your partner application was not approved",
        body=application.rejection_reason or "Your partner application was not approved at this time.",
        target_type="partner_application",
        target_id=application.id,
    )
