"""
Single consolidated daily job, intended to be invoked by PythonAnywhere's
free-tier "Scheduled Tasks" feature (see README -> "PythonAnywhere Scheduled
Task setup"). Free accounts get a limited number of daily scheduled task
slots, so this deliberately batches everything periodic into one command
rather than one task per feature.

    python manage.py run_daily_jobs

Each piece of work is a small, independently-testable service function —
this command just calls them in sequence and logs a summary. No scheduler
is involved in the unit tests for these functions (see
apps/*/tests/test_services.py); this module has its own thin
integration-style test that invokes the command itself.
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics.services import recompute_impact_stats
from apps.exchanges.services import send_exchange_reminders
from apps.listings.services import reconcile_pending_photos
from apps.requests.services import expire_stale_requests

logger = logging.getLogger("salvageme")


class Command(BaseCommand):
    help = "Runs all periodic SalvageMe jobs (expiry, stats, reminders, FileForge reconciliation)."

    def handle(self, *args, **options):
        expired_count = expire_stale_requests(threshold_days=settings.PENDING_REQUEST_EXPIRY_DAYS)
        self.stdout.write(f"Expired {expired_count} stale pending request(s).")

        snapshot = recompute_impact_stats()
        self.stdout.write(f"Recomputed impact stats: {snapshot}")

        reminder_count = send_exchange_reminders(window_hours=settings.EXCHANGE_REMINDER_WINDOW_HOURS)
        self.stdout.write(f"Sent {reminder_count} exchange reminder(s).")

        reconciled_count = reconcile_pending_photos()
        self.stdout.write(f"Reconciled {reconciled_count} stuck ListingPhoto upload(s).")

        logger.info(
            "run_daily_jobs complete: expired=%s stats=%s reminders=%s reconciled=%s",
            expired_count,
            snapshot.id,
            reminder_count,
            reconciled_count,
        )
        self.stdout.write(self.style.SUCCESS("run_daily_jobs complete."))
