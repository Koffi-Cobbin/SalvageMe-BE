import pytest

from apps.notifications.models import Notification
from apps.notifications.services import (
    notify,
    notify_exchange_completed,
    notify_report_resolved,
    notify_role_assigned,
)

pytestmark = pytest.mark.django_db


class TestNotify:
    def test_creates_notification_and_sends_email(self, user_factory, mailoutbox):
        user = user_factory(email="a@example.com")
        notification = notify(
            recipient=user, category=Notification.Category.SYSTEM, title="Hello", body="World"
        )
        assert notification.pk is not None
        assert notification.is_read is False
        assert len(mailoutbox) == 1
        assert mailoutbox[0].subject == "Hello"

    def test_send_email_false_skips_email(self, user_factory, mailoutbox):
        user = user_factory(email="b@example.com")
        notify(recipient=user, category=Notification.Category.SYSTEM, title="X", send_email=False)
        assert len(mailoutbox) == 0

    def test_email_failure_does_not_raise(self, user_factory, mocker):
        user = user_factory(email="c@example.com")
        mocker.patch("apps.notifications.services.send_mail", side_effect=Exception("boom"))
        # should not raise despite the email backend failing
        notification = notify(recipient=user, category=Notification.Category.SYSTEM, title="X")
        assert notification.pk is not None


class TestExistingWrappersStillWork:
    def test_notify_exchange_completed_notifies_both_parties(self, exchange_factory):
        exchange = exchange_factory()
        notify_exchange_completed(exchange)
        assert Notification.objects.filter(recipient=exchange.donor).count() == 1
        assert Notification.objects.filter(recipient=exchange.recipient).count() == 1


class TestNewNotifications:
    def test_notify_report_resolved(self, report_factory):
        report = report_factory()
        report.status = "resolved"
        notify_report_resolved(report)
        assert Notification.objects.filter(
            recipient=report.reporter, category=Notification.Category.REPORT_RESOLVED
        ).exists()

    def test_notify_role_assigned(self, user_factory):
        user = user_factory()
        notify_role_assigned(user, old_role_name=None, new_role_name="Volunteer")
        n = Notification.objects.get(recipient=user, category=Notification.Category.ROLE_ASSIGNED)
        assert "Volunteer" in n.title
