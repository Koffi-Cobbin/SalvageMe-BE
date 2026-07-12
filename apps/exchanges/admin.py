from django.contrib import admin

from .models import Exchange


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    """Read-mostly view for support/debugging a stuck exchange."""

    list_display = ["id", "listing", "donor", "recipient", "status", "scheduled_at", "completed_at"]
    list_filter = ["status"]
    search_fields = ["listing__title", "donor__username", "recipient__username"]
    readonly_fields = ["listing", "donor", "recipient", "completed_at"]
