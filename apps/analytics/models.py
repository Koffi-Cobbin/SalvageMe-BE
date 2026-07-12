from django.db import models


class ImpactStatsSnapshot(models.Model):
    """
    A single cached row of aggregate impact stats, recomputed daily by
    `run_daily_jobs` (see ASYNC & SCHEDULED WORK). We keep this as a model
    row rather than only Django's cache framework so the last-known-good
    numbers survive a cache eviction/restart, and so /api/stats/impact/
    always has something to serve even before the first scheduled run.
    """

    total_listings = models.PositiveIntegerField(default=0)
    total_exchanges_completed = models.PositiveIntegerField(default=0)
    total_active_donors = models.PositiveIntegerField(default=0)
    total_active_recipients = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-computed_at"]
        get_latest_by = "computed_at"

    def __str__(self):
        return f"Impact stats as of {self.computed_at}"
