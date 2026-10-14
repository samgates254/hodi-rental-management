from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.organizations.models import OrganizationMembership
from apps.tenants.models import Tenant

from .models import RentPayment
from .serializers import RentPaymentSerializer


READ_ROLES = (
	OrganizationMembership.Role.OWNER,
	OrganizationMembership.Role.PROPERTY_MANAGER,
	OrganizationMembership.Role.ACCOUNTANT,
	OrganizationMembership.Role.CARETAKER,
)
WRITE_ROLES = (
	OrganizationMembership.Role.OWNER,
	OrganizationMembership.Role.PROPERTY_MANAGER,
	OrganizationMembership.Role.ACCOUNTANT,
)


class RentPaymentViewSet(viewsets.ModelViewSet):
	"""Read-only historical pre-ledger receipt records.

	New receipts must use the canonical manual-receipt endpoint so they create
	allocations and ledger postings atomically. Historical rows remain visible
	for audit and reporting but cannot be changed into a financial event.
	"""
	http_method_names = ('get', 'head', 'options')
	serializer_class = RentPaymentSerializer
	permission_classes = (permissions.IsAuthenticated,)

	def get_queryset(self):
		queryset = RentPayment.objects.filter(
			Q(
				lease__tenant__organization__memberships__user=self.request.user,
				lease__tenant__organization__memberships__is_active=True,
				lease__tenant__organization__memberships__organization__is_active=True,
				lease__tenant__organization__memberships__role__in=READ_ROLES,
			)
			| Q(
				lease__tenant__user=self.request.user,
				lease__tenant__is_active=True,
				lease__tenant__organization__is_active=True,
			)
		).select_related('lease', 'lease__tenant', 'lease__unit', 'recorded_by').distinct()
		organization_id = self.request.query_params.get('organization')
		if organization_id:
			try:
				organization_id = int(organization_id)
			except ValueError as error:
				raise ValidationError({
					'organization': 'A valid organization ID is required.',
				}) from error
			queryset = queryset.filter(lease__tenant__organization_id=organization_id)
		return queryset

	def check_permissions(self, request):
		super().check_permissions(request)
		write = request.method not in permissions.SAFE_METHODS
		roles = WRITE_ROLES if write else READ_ROLES
		has_staff_access = OrganizationMembership.objects.filter(
			user=request.user,
			is_active=True,
			organization__is_active=True,
			role__in=roles,
		).exists()
		has_tenant_read_access = not write and Tenant.objects.filter(
			user=request.user,
			is_active=True,
			organization__is_active=True,
		).exists()
		if not has_staff_access and not has_tenant_read_access:
			raise PermissionDenied('You do not have permission to access rent payments.')

	def perform_create(self, serializer):
		lease = serializer.validated_data['lease']
		self.ensure_write_access(lease.organization_id)
		serializer.save(recorded_by=self.request.user)

	def perform_update(self, serializer):
		self.ensure_write_access(serializer.instance.organization_id)
		lease = serializer.validated_data.get('lease', serializer.instance.lease)
		self.ensure_write_access(lease.organization_id)
		serializer.save()

	def perform_destroy(self, instance):
		self.ensure_write_access(instance.organization_id)
		instance.delete()

	def ensure_write_access(self, organization_id):
		if not OrganizationMembership.objects.filter(
			user=self.request.user,
			organization_id=organization_id,
			is_active=True,
			organization__is_active=True,
			role__in=WRITE_ROLES,
		).exists():
			raise PermissionDenied('You cannot record payments for this organization.')
