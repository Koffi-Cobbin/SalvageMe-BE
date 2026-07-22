"""
Tests for the Django Admin (built-in /admin/ site) form for AdminRole —
distinct from apps/accounts/tests/test_admin_api.py, which covers the
DRF /api/v1/admin/ API. This file is specifically about the
capabilities field rendering as a pick-list in the Django Admin UI.
"""
import pytest
from django.urls import reverse

from apps.accounts.admin import AdminRoleForm
from apps.accounts.models import AdminRole
from common.admin_capabilities import ALL_CAPABILITIES

pytestmark = pytest.mark.django_db


@pytest.fixture
def django_admin_client(client, user_factory):
    superuser = user_factory(username="djangosuper", is_staff=True, is_superuser=True, password="AdminPass123!")
    client.force_login(superuser)
    return client


class TestAdminRoleFormWidget:
    def test_capabilities_field_offers_full_vocabulary_as_choices(self):
        form = AdminRoleForm()
        choice_codes = {code for code, _label in form.fields["capabilities"].choices}
        assert choice_codes == set(ALL_CAPABILITIES.keys())

    def test_capabilities_field_uses_filtered_select_multiple(self):
        from django.contrib.admin.widgets import FilteredSelectMultiple

        form = AdminRoleForm()
        assert isinstance(form.fields["capabilities"].widget, FilteredSelectMultiple)

    def test_existing_role_prepopulates_selected_capabilities(self, admin_role_factory):
        role = admin_role_factory(capabilities=["users.view", "reports.view"])
        form = AdminRoleForm(instance=role)
        assert set(form.initial["capabilities"]) == {"users.view", "reports.view"}


class TestAdminRoleChangeFormRendersInDjangoAdmin:
    def test_add_page_renders_capability_checkboxes(self, django_admin_client):
        url = reverse("admin:accounts_adminrole_add")
        response = django_admin_client.get(url)
        assert response.status_code == 200
        # Every capability code should appear as a selectable option.
        content = response.content.decode()
        assert "users.view" in content
        assert "roles.manage" in content

    def test_submitting_selected_capabilities_saves_correctly(self, django_admin_client):
        url = reverse("admin:accounts_adminrole_add")
        response = django_admin_client.post(
            url,
            {
                "name": "Content Moderator",
                "description": "Handles moderation.",
                "capabilities": ["listings.remove_restore", "reports.resolve"],
                "is_protected": False,
            },
        )
        # A successful admin add redirects (302); a form error would re-render (200).
        assert response.status_code == 302, response.content.decode()[:2000]

        role = AdminRole.objects.get(name="Content Moderator")
        assert set(role.capabilities) == {"listings.remove_restore", "reports.resolve"}

    def test_change_page_prepopulates_existing_selection(self, django_admin_client, admin_role_factory):
        role = admin_role_factory(name="Existing Role", capabilities=["dashboard.view"])
        url = reverse("admin:accounts_adminrole_change", args=[role.id])
        response = django_admin_client.get(url)
        assert response.status_code == 200
        # The selected option should be marked selected in the rendered HTML.
        assert 'value="dashboard.view" selected' in response.content.decode()
