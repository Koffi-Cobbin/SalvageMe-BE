from django.db import migrations

from common.admin_capabilities import ALL_CAPABILITIES


def seed_admin_role(apps, schema_editor):
    AdminRole = apps.get_model("accounts", "AdminRole")
    User = apps.get_model("accounts", "User")

    admin_role, _ = AdminRole.objects.get_or_create(
        name="Admin",
        defaults={
            "description": "Full access to every admin capability. Built-in and protected.",
            "capabilities": sorted(ALL_CAPABILITIES.keys()),
            "is_protected": True,
        },
    )

    # Nobody who currently has Django Admin access should silently lose the
    # equivalent in the new API — carry is_staff=True users forward onto
    # the built-in role.
    User.objects.filter(is_staff=True, admin_role__isnull=True).update(admin_role=admin_role)


def unseed_admin_role(apps, schema_editor):
    AdminRole = apps.get_model("accounts", "AdminRole")
    AdminRole.objects.filter(name="Admin", is_protected=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_adminrole_user_admin_role"),
    ]

    operations = [
        migrations.RunPython(seed_admin_role, unseed_admin_role),
    ]
