from django.contrib import admin

from . import services
from .models import AuditLog, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "target_type", "target_id", "reason", "status", "reporter", "created_at"]
    list_filter = ["status", "reason", "target_type"]
    search_fields = ["reporter__username", "detail"]
    actions = ["resolve_reports", "dismiss_reports"]

    @admin.action(description="Resolve selected reports")
    def resolve_reports(self, request, queryset):
        count = 0
        for report in queryset.filter(status=Report.Status.OPEN):
            services.resolve_report(report=report, acting_user=request.user, outcome=Report.Status.RESOLVED)
            count += 1
        self.message_user(request, f"Resolved {count} report(s).")

    @admin.action(description="Dismiss selected reports")
    def dismiss_reports(self, request, queryset):
        count = 0
        for report in queryset.filter(status=Report.Status.OPEN):
            services.resolve_report(report=report, acting_user=request.user, outcome=Report.Status.DISMISSED)
            count += 1
        self.message_user(request, f"Dismissed {count} report(s).")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["id", "action", "target_type", "target_id", "actor", "created_at"]
    list_filter = ["action", "target_type"]
    search_fields = ["actor__username"]
    readonly_fields = ["actor", "action", "target_type", "target_id", "metadata", "created_at"]

    def has_add_permission(self, request):
        return False
