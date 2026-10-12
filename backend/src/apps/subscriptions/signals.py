from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.organizations.models import Organization

from .models import SubscriptionPlan
from .services import get_or_create_free_subscription


@receiver(post_save, sender=Organization)
def create_free_organization_subscription(sender, instance, created, **kwargs):
    # TransactionTestCase flushes data-migration seed rows between tests.
    # On a deployed database the catalogue is installed by the migration.
    if created and SubscriptionPlan.objects.filter(code='free', is_active=True).exists():
        get_or_create_free_subscription(instance)
