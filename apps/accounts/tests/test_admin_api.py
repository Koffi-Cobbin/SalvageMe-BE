import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


class TestAdminMe:
    def test_requires_auth(self, api_client):
        response = api_client.get(reverse("admin-me"))
        assert response.status_code == 401

    def test_normal_user_gets_no_admin_access(self, auth_client):
        client, user = auth_client(username="normie")
        response = client.get(reverse("admin-me"))
        assert response.status_code == 200
        assert response.data["can_access_admin"] is False
        assert response.data["admin_role"] is None
        assert response.data["capabilities"] == []

    def test_role_holder_sees_capabilities(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["listings.view", "reports.view"])
        client, user = auth_client(admin_role=role)
        response = client.get(reverse("admin-me"))
        assert response.data["can_access_admin"] is True
        assert set(response.data["capabilities"]) == {"listings.view", "reports.view"}


class TestCapabilitiesList:
    def test_requires_roles_manage(self, auth_client):
        client, user = auth_client(username="nocap")
        response = client.get(reverse("admin-capabilities"))
        assert response.status_code == 403

    def test_role_manager_can_view(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["roles.manage"])
        client, user = auth_client(admin_role=role)
        response = client.get(reverse("admin-capabilities"))
        assert response.status_code == 200
        assert any(c["code"] == "users.view" for c in response.data)


class TestAdminRoleViewSet:
    def test_list_requires_capability(self, auth_client):
        client, user = auth_client(username="norolemgr")
        response = client.get(reverse("admin-role-list"))
        assert response.status_code == 403

    def test_create_role(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["roles.manage"])
        client, user = auth_client(admin_role=role)
        response = client.post(
            reverse("admin-role-list"), {"name": "Volunteer", "capabilities": ["listings.view"]}
        )
        assert response.status_code == 201
        assert response.data["name"] == "Volunteer"

    def test_create_role_unknown_capability_rejected(self, auth_client, admin_role_factory):
        role = admin_role_factory(capabilities=["roles.manage"])
        client, user = auth_client(admin_role=role)
        response = client.post(reverse("admin-role-list"), {"name": "Bad", "capabilities": ["nope"]})
        assert response.status_code == 400

    def test_delete_protected_role_rejected(self, auth_client, admin_role_factory):
        manager_role = admin_role_factory(capabilities=["roles.manage"])
        client, user = auth_client(admin_role=manager_role)
        protected = admin_role_factory(is_protected=True, capabilities=["roles.manage"])
        response = client.delete(reverse("admin-role-detail", args=[protected.id]))
        assert response.status_code == 400


class TestAdminUserViewSet:
    def test_list_requires_users_view(self, auth_client):
        client, user = auth_client(username="nouserview")
        response = client.get(reverse("admin-user-list"))
        assert response.status_code == 403

    def test_list_with_capability(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.view"])
        client, viewer = auth_client(admin_role=role)
        user_factory.create_batch(3)
        response = client.get(reverse("admin-user-list"))
        assert response.status_code == 200

    def test_suspend_requires_capability(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.view"])  # no users.suspend
        client, actor = auth_client(admin_role=role)
        target = user_factory()
        response = client.post(reverse("admin-user-suspend", args=[target.id]))
        assert response.status_code == 403

    def test_suspend_success(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.suspend"])
        client, actor = auth_client(admin_role=role)
        target = user_factory()
        response = client.post(reverse("admin-user-suspend", args=[target.id]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is False

    def test_suspend_already_suspended_rejected(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.suspend"])
        client, actor = auth_client(admin_role=role)
        target = user_factory(is_active=False)
        response = client.post(reverse("admin-user-suspend", args=[target.id]))
        assert response.status_code == 400

    def test_assign_role_requires_roles_manage(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.suspend"])  # not roles.manage
        client, actor = auth_client(admin_role=role)
        target = user_factory()
        response = client.post(reverse("admin-user-assign-role", args=[target.id]), {"admin_role_id": role.id})
        assert response.status_code == 403

    def test_assign_role_success(self, auth_client, admin_role_factory, user_factory):
        manager_role = admin_role_factory(capabilities=["roles.manage"])
        target_role = admin_role_factory(capabilities=["listings.view"])
        client, actor = auth_client(admin_role=manager_role)
        target = user_factory()
        response = client.post(
            reverse("admin-user-assign-role", args=[target.id]), {"admin_role_id": target_role.id}
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.admin_role_id == target_role.id

    def test_patch_user_requires_users_edit(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.view"])  # not users.edit
        client, actor = auth_client(admin_role=role)
        target = user_factory()
        response = client.patch(reverse("admin-user-detail", args=[target.id]), {"is_verified": True})
        assert response.status_code == 403

    def test_patch_user_success(self, auth_client, admin_role_factory, user_factory):
        role = admin_role_factory(capabilities=["users.edit"])
        client, actor = auth_client(admin_role=role)
        target = user_factory()
        response = client.patch(reverse("admin-user-detail", args=[target.id]), {"is_verified": True})
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_verified is True
