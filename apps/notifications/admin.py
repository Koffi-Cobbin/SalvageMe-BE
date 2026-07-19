from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "recipient", "category", "title", "is_read", "created_at"]
    list_filter = ["category", "is_read"]
    search_fields = ["recipient__username", "title"]
    readonly_fields = ["recipient", "category", "title", "body", "target_type", "target_id", "created_at"]
