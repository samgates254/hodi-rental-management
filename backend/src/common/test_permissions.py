from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Organization, OrganizationMembership
from common.permissions import (
    RESOURCE_ROLE_ACCESS,
    OrganizationRolePermission,
    action_for_method,
    user_can_access_organization_resource,
)


class OrganizationResourceRolePolicyTests(TestCase):
    def test_all_resource_actions_match_the_role_matrix(self):
        user = get_user_model().objects.create_user(
            username='role-matrix-user',
            password='password',
        )
        roles = [role for role, _label in OrganizationMembership.Role.choices]
        organizations = {}
        for index, role in enumerate(roles):
            organization = Organization.objects.create(name=f'Organization {index}')
            OrganizationMembership.objects.create(
                organization=organization,
                user=user,
                role=role,
            )
            organizations[role] = organization

        for resource, actions in RESOURCE_ROLE_ACCESS.items():
            for action in ('read', 'write'):
                expected_roles = set(actions[action])
                for role, organization in organizations.items():
                    with self.subTest(resource=resource, action=action, role=role):
                        self.assertEqual(
                            user_can_access_organization_resource(
                                user,
                                organization.pk,
                                resource,
                                action,
                            ),
                            role in expected_roles,
                        )

    def test_permission_class_uses_http_method_and_resource_policy(self):
        user = get_user_model().objects.create_user(
            username='permission-class-user',
            password='password',
        )
        permission = OrganizationRolePermission()

        for resource, actions in RESOURCE_ROLE_ACCESS.items():
            for action, method in (('read', 'GET'), ('write', 'POST')):
                organization = Organization.objects.create(
                    name=f'{resource}-{action}',
                )
                for role in OrganizationMembership.Role:
                    OrganizationMembership.objects.create(
                        organization=organization,
                        user=user,
                        role=role,
                    )
                    request = SimpleNamespace(method=method, user=user)
                    view = SimpleNamespace(organization_resource=resource)

                    with self.subTest(resource=resource, action=action, role=role):
                        self.assertEqual(
                            permission.has_permission(request, view),
                            role.value in actions[action],
                        )

                    user.organization_memberships.filter(
                        organization=organization,
                    ).delete()

    def test_http_methods_are_classified_as_read_or_write(self):
        for method in ('GET', 'HEAD', 'OPTIONS'):
            self.assertEqual(action_for_method(method), 'read')
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(action_for_method(method), 'write')