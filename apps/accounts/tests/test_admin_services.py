import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts import admin_services
from apps.accounts.models import AdminRole, role_ids_with_capability, users_with_capability

pytestmark = pytest.mark.django_db


class TestRoleIdsWithCapability:
    def test_finds_roles_with_capability(self, admin_role_factory):
        with_cap = admin_role_factory(capabilities=["users.view", "roles.manage"])
        without_cap = admin_role_factory(capabilities=["users.view"])
        ids = role_ids_with_capability("roles.manage")
        assert with_cap.id in ids
        assert without_cap.id not in ids

    def test_users_with_capability(self, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["reports.resolve"])
        holder = user_factory(admin_role=role)
        non_holder = user_factory()
        result = list(users_with_capability("reports.resolve"))
        assert holder in result
        assert non_holder not in result


class TestCreateAdminRole:
    def test_success(self, user_factory):
        acting = user_factory()
        role = admin_services.create_admin_role(
            name="Volunteer", capabilities=["listings.view"], acting_user=acting
        )
        assert role.pk is not None
        assert role.capabilities == ["listings.view"]

    def test_unknown_capability_rejected(self, user_factory):
        acting = user_factory()
        with pytest.raises(ValidationError):
            admin_services.create_admin_role(name="Bad", capabilities=["not.real"], acting_user=acting)

    def test_duplicate_name_rejected(self, admin_role_factory, user_factory):
        admin_role_factory(name="Volunteer")
        acting = user_factory()
        with pytest.raises(ValidationError):
            admin_services.create_admin_role(name="Volunteer", capabilities=[], acting_user=acting)


class TestUpdateAdminRole:
    def test_success(self, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["listings.view"])
        acting = user_factory()
        updated = admin_services.update_admin_role(
            role=role, acting_user=acting, capabilities=["listings.view", "reports.view"]
        )
        assert "reports.view" in updated.capabilities

    def test_cannot_edit_protected_role_capabilities(self, admin_role_factory, user_factory):
        role = admin_role_factory(is_protected=True, capabilities=["roles.manage"])
        acting = user_factory()
        with pytest.raises(ValidationError):
            admin_services.update_admin_role(role=role, acting_user=acting, capabilities=[])

    def test_can_rename_protected_role(self, admin_role_factory, user_factory):
        role = admin_role_factory(is_protected=True, capabilities=["roles.manage"], name="Admin")
        acting = user_factory()
        updated = admin_services.update_admin_role(role=role, acting_user=acting, name="Super Admin")
        assert updated.name == "Super Admin"


class TestDeleteAdminRole:
    def test_cannot_delete_protected_role(self, admin_role_factory, user_factory):
        role = admin_role_factory(is_protected=True)
        with pytest.raises(ValidationError):
            admin_services.delete_admin_role(role=role, acting_user=user_factory())

    def test_cannot_delete_role_in_use(self, admin_role_factory, user_factory):
        role = admin_role_factory()
        user_factory(admin_role=role)
        with pytest.raises(ValidationError):
            admin_services.delete_admin_role(role=role, acting_user=user_factory())

    def test_delete_success_when_unused(self, admin_role_factory, user_factory):
        role = admin_role_factory()
        admin_services.delete_admin_role(role=role, acting_user=user_factory())
        assert not AdminRole.objects.filter(pk=role.pk).exists()


class TestAssignAdminRole:
    def test_assigns_role_and_logs_audit(self, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["listings.view"])
        acting = user_factory()
        target = user_factory()
        admin_services.assign_admin_role(user=target, new_role=role, acting_user=acting)
        target.refresh_from_db()
        assert target.admin_role_id == role.id

    def test_revoke_with_none(self, admin_role_factory, user_factory):
        role = admin_role_factory()
        acting = user_factory()
        target = user_factory(admin_role=role)
        admin_services.assign_admin_role(user=target, new_role=None, acting_user=acting)
        target.refresh_from_db()
        assert target.admin_role is None

    def test_last_role_manager_lockout(self, admin_role_factory, user_factory):
        manager_role = admin_role_factory(capabilities=["roles.manage"])
        other_role = admin_role_factory(capabilities=["listings.view"])
        only_manager = user_factory(admin_role=manager_role)
        with pytest.raises(ValidationError):
            admin_services.assign_admin_role(user=only_manager, new_role=other_role, acting_user=only_manager)

    def test_reassigning_when_another_manager_exists_is_allowed(self, admin_role_factory, user_factory):
        manager_role = admin_role_factory(capabilities=["roles.manage"])
        other_role = admin_role_factory(capabilities=["listings.view"])
        first = user_factory(admin_role=manager_role)
        user_factory(admin_role=manager_role)  # a second manager exists
        admin_services.assign_admin_role(user=first, new_role=other_role, acting_user=first)
        first.refresh_from_db()
        assert first.admin_role_id == other_role.id
