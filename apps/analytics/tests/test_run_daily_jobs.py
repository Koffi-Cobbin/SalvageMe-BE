import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.requests.models import BookRequest

pytestmark = pytest.mark.django_db


def test_run_daily_jobs_end_to_end(book_request_factory, exchange_factory, mocker):
    # An old pending request that should expire.
    stale = book_request_factory()
    BookRequest.objects.filter(pk=stale.pk).update(created_at=timezone.now() - datetime.timedelta(days=30))

    # An exchange due soon that should get a reminder.
    exchange_factory(scheduled_at=timezone.now() + timezone.timedelta(hours=2))

    mocker.patch("apps.listings.services.get_fileforge_client")

    call_command("run_daily_jobs")

    stale.refresh_from_db()
    assert stale.status == BookRequest.Status.CANCELLED

    from apps.analytics.models import ImpactStatsSnapshot

    assert ImpactStatsSnapshot.objects.exists()
