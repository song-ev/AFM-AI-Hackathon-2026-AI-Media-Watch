"""Merge the old four roles into two (analyst, bank_admin).

afm_lead and system_admin no longer exist; existing users carrying them are
migrated to `analyst`. Former system_admins additionally become Django
superusers (user management is now a superuser capability, not a role).
"""
from django.db import migrations


def merge_roles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="system_admin").update(
        role="analyst", is_superuser=True, is_staff=True
    )
    User.objects.filter(role="afm_lead").update(role="analyst")


def noop(apps, schema_editor):
    # Irreversible: the old roles are gone; leave users as analyst.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_user_role"),
    ]

    operations = [
        migrations.RunPython(merge_roles, noop),
    ]
