from django.contrib import admin

from .models import BookRequest


@admin.register(BookRequest)
class BookRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "listing", "requester", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["listing__title", "requester__username"]
