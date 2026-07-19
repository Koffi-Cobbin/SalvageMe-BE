from rest_framework.routers import DefaultRouter

from .admin_views import AdminAuditLogViewSet, AdminReportViewSet

router = DefaultRouter()
router.register("reports", AdminReportViewSet, basename="admin-report")
router.register("audit-log", AdminAuditLogViewSet, basename="admin-auditlog")

urlpatterns = router.urls
