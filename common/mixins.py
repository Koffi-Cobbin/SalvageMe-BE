from django.db import models


class TimestampedModel(models.Model):
    """Adds created_at/updated_at to any model that inherits from it."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLoggingMixin:
    """
    Mixin for ViewSets/service functions that perform moderation-style
    actions. Provides a single helper so every moderation action writes an
    AuditLog entry the same way — see apps/moderation/services.py for the
    underlying write.
    """

    def write_audit_log(self, *, actor, action, target_type, target_id, metadata=None):
        from apps.moderation.services import record_audit_log

        record_audit_log(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
        )
