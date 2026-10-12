from django.conf import settings
from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower


INDEX_NAME = 'accounts_user_email_ci_uniq'


def duplicate_email_group_count(user_model):
    return (
        user_model.objects.exclude(email='')
        .annotate(email_key=Lower('email'))
        .values('email_key')
        .annotate(email_count=Count('pk'))
        .filter(email_count__gt=1)
        .count()
    )


def check_existing_emails(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    user_model = apps.get_model(app_label, model_name)
    duplicate_groups = duplicate_email_group_count(user_model)
    if duplicate_groups:
        raise RuntimeError(
            'Cannot enforce case-insensitive email uniqueness: found '
            f'{duplicate_groups} groups with duplicate non-empty emails. '
            'Resolve these records without deleting or merging accounts, then retry.'
        )


def create_email_index(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    user_model = apps.get_model(app_label, model_name)
    table = schema_editor.quote_name(user_model._meta.db_table)
    email_column = schema_editor.quote_name(user_model._meta.get_field('email').column)
    index = schema_editor.quote_name(INDEX_NAME)
    schema_editor.execute(
        f'CREATE UNIQUE INDEX {index} ON {table} (LOWER({email_column})) '
        f"WHERE {email_column} <> ''"
    )


def remove_email_index(apps, schema_editor):
    index = schema_editor.quote_name(INDEX_NAME)
    schema_editor.execute(f'DROP INDEX {index}')


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_accountprofile_account_type_and_more'),
        # SQLite rebuilds auth_user during later built-in auth migrations;
        # create the unmanaged functional index after those rebuilds finish.
        ('auth', '0012_alter_user_first_name_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(check_existing_emails, migrations.RunPython.noop),
        migrations.RunPython(create_email_index, remove_email_index),
    ]
