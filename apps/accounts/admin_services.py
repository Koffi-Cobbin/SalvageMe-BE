"""
Service-layer functions backing the admin role/capability endpoints — see
docs/ADMIN_API_PLAN.md. Kept in a separate module from apps/accounts/services.py
(which doesn't exist yet otherwise) since this is specifically the admin-role
management surface, mirroring the admin_serializers.py / admin_views.py split.
"""
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from rest_framework.exceptions import ValidationError

from common.admin_capabilities import is_valid_capability
from apps.moderation.services import record_audit_log
from apps.notifications.services import notify_role_assigned

from .models import AdminRole, User, role_ids_with_capability


def _validate_capabilities(capabilities: list[str]) -> None:
    invalid = [c for c in capabilities if not is_valid_capability(c)]
    if invalid:
        raise ValidationError(
            {"detail": f"Unknown capability code(s): {invalid}", "code": "unknown_capability"}
        )


def create_admin_role(*, name: str, description: str = "", capabilities: list[str], acting_user) -> AdminRole:
    _validate_capabilities(capabilities)
    try:
        with transaction.atomic():
            role = AdminRole.objects.create(name=name, description=description, capabilities=capabilities)
    except IntegrityError as exc:
        raise ValidationError({"detail": "A role with this name already exists.", "code": "duplicate_name"}) from exc

    record_audit_log(
        actor=acting_user, action="role_created", target_type="admin_role", target_id=role.id,
        metadata={"name": role.name, "capabilities": role.capabilities},
    )
    return role


def update_admin_role(*, role: AdminRole, acting_user, name=None, description=None, capabilities=None) -> AdminRole:
    if capabilities is not None and role.is_protected:
        raise ValidationError(
            {"detail": "The built-in role's capabilities cannot be edited.", "code": "role_protected"}
        )

    diff = {}
    if name is not None and name != role.name:
        diff["name"] = {"old": role.name, "new": name}
        role.name = name
    if description is not None and description != role.description:
        role.description = description
    if capabilities is not None:
        _validate_capabilities(capabilities)
        diff["capabilities"] = {"old": role.capabilities, "new": capabilities}
        role.capabilities = capabilities

    try:
        role.save()
    except IntegrityError as exc:
        raise ValidationError({"detail": "A role with this name already exists.", "code": "duplicate_name"}) from exc

    if diff:
        record_audit_log(
            actor=acting_user, action="role_updated", target_type="admin_role", target_id=role.id, metadata=diff
        )
    return role


def delete_admin_role(*, role: AdminRole, acting_user) -> None:
    if role.is_protected:
        raise ValidationError({"detail": "The built-in role cannot be deleted.", "code": "role_protected"})

    role_id, role_name = role.id, role.name

    try:
        role.delete()
    except ProtectedError as exc:
        raise ValidationError(
            {"detail": "This role is currently assigned to one or more users.", "code": "role_in_use"}
        ) from exc

    record_audit_log(
        actor=acting_user, action="role_deleted", target_type="admin_role", target_id=role_id,
        metadata={"name": role_name},
    )


def assign_admin_role(*, user: User, new_role: AdminRole | None, acting_user) -> User:
    old_role = user.admin_role

    if old_role == new_role:
        return user  # no-op, nothing to guard or log

    # Safeguard: never leave zero users able to manage roles at all. This is
    # the generalized version of a "last admin" check — with dynamic roles,
    # what matters is whether anyone can still reach roles.manage, not
    # whether a specific role name still has a holder.
    if old_role and "roles.manage" in old_role.capabilities:
        still_has_manager = (
            User.objects.filter(admin_role_id__in=role_ids_with_capability("roles.manage"))
            .exclude(pk=user.pk)
            .exists()
        )
        new_role_has_manage = bool(new_role and "roles.manage" in new_role.capabilities)
        if not still_has_manager and not new_role_has_manage:
            raise ValidationError(
                {
                    "detail": "This would leave no user able to manage roles.",
                    "code": "last_role_manager",
                }
            )

    user.admin_role = new_role
    # Keep is_staff in sync so Django Admin access (and any legacy
    # is_staff-gated backstop checks elsewhere in the codebase, e.g.
    # apps/moderation/services.py::resolve_report) still work for whoever
    # holds a role — see docs/ADMIN_API_PLAN.md "Relationship to Django's
    # is_staff/is_superuser".
    user.is_staff = new_role is not None
    user.save(update_fields=["admin_role", "is_staff"])

    record_audit_log(
        actor=acting_user, action="user_role_assigned", target_type="user", target_id=user.id,
        metadata={
            "old_role_id": old_role.id if old_role else None,
            "new_role_id": new_role.id if new_role else None,
        },
    )
    notify_role_assigned(
        user, old_role_name=old_role.name if old_role else None, new_role_name=new_role.name if new_role else None
    )
    return user
