from django.db.models import QuerySet


def organization_ids_for_user(user):
    return user.organization_memberships.filter(
        is_active=True,
        organization__is_active=True,
    ).values_list('organization_id', flat=True)


def scoped_queryset(queryset: QuerySet, user, organization_field: str) -> QuerySet:
    return queryset.filter(
        **{f'{organization_field}__in': organization_ids_for_user(user)},
    )
