"""Organization staff roles that owners can create and manage as a team."""

from .models import OrganizationMembership


STAFF_ROLE_VALUES = (
    OrganizationMembership.Role.PROPERTY_MANAGER,
    OrganizationMembership.Role.CARETAKER,
    OrganizationMembership.Role.TECHNICIAN,
)

STAFF_ROLE_CHOICES = tuple(
    (role, OrganizationMembership.Role(role).label)
    for role in STAFF_ROLE_VALUES
)


def ensure_role_profile(user, role):
    if role == OrganizationMembership.Role.TECHNICIAN:
        from apps.maintenance.models import TechnicianProfile

        TechnicianProfile.objects.get_or_create(user=user)
