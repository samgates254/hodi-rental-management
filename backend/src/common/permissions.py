from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.organizations.models import OrganizationMembership


RESOURCE_ROLE_ACCESS = {
    'properties': {
        'read': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.ACCOUNTANT,
            OrganizationMembership.Role.CARETAKER,
        ),
        'write': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
        ),
    },
    'leases': {
        'read': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.ACCOUNTANT,
        ),
        'write': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
        ),
    },
    'billing': {
        'read': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.ACCOUNTANT,
        ),
        'write': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ACCOUNTANT,
        ),
    },
    'maintenance': {
        'read': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.CARETAKER,
        ),
        'write': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.CARETAKER,
        ),
    },
    'tenants': {
        'read': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
            OrganizationMembership.Role.ACCOUNTANT,
            OrganizationMembership.Role.CARETAKER,
        ),
        'write': (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.PROPERTY_MANAGER,
        ),
    },
}


def action_for_method(method):
    return 'read' if method in SAFE_METHODS else 'write'


def organization_ids_for_resource(user, resource, action):
    roles = RESOURCE_ROLE_ACCESS[resource][action]
    return user.organization_memberships.filter(
        is_active=True,
        organization__is_active=True,
        role__in=roles,
    ).values_list('organization_id', flat=True)


def user_can_access_organization_resource(user, organization_id, resource, action):
    return user.organization_memberships.filter(
        organization_id=organization_id,
        organization__is_active=True,
        is_active=True,
        role__in=RESOURCE_ROLE_ACCESS[resource][action],
    ).exists()


def organization_id_for_object(instance):
    organization_id = getattr(instance, 'organization_id', None)
    if organization_id is not None:
        return organization_id

    for relation_name in ('property', 'building', 'lease', 'tenant', 'unit'):
        related = getattr(instance, relation_name, None)
        if related is not None:
            organization_id = organization_id_for_object(related)
            if organization_id is not None:
                return organization_id

    return None


class OrganizationRolePermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        resource = view.organization_resource
        action = action_for_method(request.method)
        return organization_ids_for_resource(
            request.user,
            resource,
            action,
        ).exists()

    def has_object_permission(self, request, view, obj):
        organization_id = organization_id_for_object(obj)
        return organization_id is not None and user_can_access_organization_resource(
            request.user,
            organization_id,
            view.organization_resource,
            action_for_method(request.method),
        )