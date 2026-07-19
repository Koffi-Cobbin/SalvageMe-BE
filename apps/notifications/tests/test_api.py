import pytest
from django.urls import reverse

from apps.notifications.models import Notification
from apps.notifications.services import notify

pytestmark = pytest.mark.django_db


def make_notification(user, is_read=False):
    n = notify(recipient=user, category=Notification.Category.SYSTEM, title="Test", send_email=False)
    if is_read:
        n.mark_read()
    return n


class TestListNotifications:
    def test_requires_auth(self, api_client):
        response = api_client.get(reverse("notification-list"))
        assert response.status_code == 401

    def test_scoped_to_current_user(self, auth_client, user_factory):
        client, user = auth_client(username="notifuser")
        mine = make_notification(user)
        other = user_factory(username="other")
        make_notification(other)
        response = client.get(reverse("notification-list"))
        ids = [n["id"] for n in response.data["results"]]
        assert mine.id in ids
        assert len(ids) == 1

    def test_filter_by_is_read(self, auth_client):
        client, user = auth_client(username="notifuser2")
        unread = make_notification(user, is_read=False)
        make_notification(user, is_read=True)
        response = client.get(reverse("notification-list"), {"is_read": "false"})
        ids = [n["id"] for n in response.data["results"]]
        assert ids == [unread.id]


class TestUnreadCount:
    def test_unread_count(self, auth_client):
        client, user = auth_client(username="notifuser3")
        make_notification(user, is_read=False)
        make_notification(user, is_read=False)
        make_notification(user, is_read=True)
        response = client.get(reverse("notification-unread-count"))
        assert response.status_code == 200
        assert response.data["count"] == 2


class TestMarkRead:
    def test_mark_single_read(self, auth_client):
        client, user = auth_client(username="notifuser4")
        n = make_notification(user)
        response = client.post(reverse("notification-read", args=[n.id]))
        assert response.status_code == 200
        n.refresh_from_db()
        assert n.is_read is True

    def test_cannot_mark_other_users_notification(self, auth_client, user_factory):
        other = user_factory(username="otheruser")
        n = make_notification(other)
        client, user = auth_client(username="notifuser5")
        response = client.post(reverse("notification-read", args=[n.id]))
        assert response.status_code == 404

    def test_mark_all_read(self, auth_client):
        client, user = auth_client(username="notifuser6")
        make_notification(user)
        make_notification(user)
        response = client.post(reverse("notification-mark-all-read"))
        assert response.status_code == 200
        assert response.data["marked_read"] == 2
        assert Notification.objects.filter(recipient=user, is_read=False).count() == 0


class TestDeleteNotification:
    def test_delete_own_notification(self, auth_client):
        client, user = auth_client(username="notifuser7")
        n = make_notification(user)
        response = client.delete(reverse("notification-detail", args=[n.id]))
        assert response.status_code == 204
        assert not Notification.objects.filter(pk=n.id).exists()
