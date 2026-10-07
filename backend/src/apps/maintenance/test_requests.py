from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AccountProfile
from apps.audit.models import AuditLog
from apps.leases.models import Lease
from apps.maintenance.models import MaintenanceRequest, TechnicianProfile
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant


class MaintenanceRequestApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='owner', password='password')
        self.caretaker = user_model.objects.create_user(username='caretaker', password='password')
        self.accountant = user_model.objects.create_user(username='accountant', password='password')
        self.technician = user_model.objects.create_user(username='tech', password='password')
        self.other_tech = user_model.objects.create_user(username='other-tech', password='password')
        self.tenant_user = user_model.objects.create_user(username='tenant', password='password')
        self.organization = Organization.objects.create(name='Rongai Homes')
        self.other = Organization.objects.create(name='Other Homes')
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.owner, role=OrganizationMembership.Role.OWNER,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.caretaker, role=OrganizationMembership.Role.CARETAKER,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.accountant, role=OrganizationMembership.Role.ACCOUNTANT,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.technician, role=OrganizationMembership.Role.TECHNICIAN,
        )
        OrganizationMembership.objects.create(
            organization=self.other, user=self.other_tech, role=OrganizationMembership.Role.TECHNICIAN,
        )
        AccountProfile.objects.create(
            user=self.technician,
            account_type=AccountProfile.AccountType.SERVICE_PROFESSIONAL,
            professional_trade=AccountProfile.ProfessionalTrade.PLUMBER,
        )
        TechnicianProfile.objects.create(
            user=self.technician,
            trade='PLUMBER',
            skills=['PLUMBER'],
            rating_milli=4000,
            acceptance_milli=800,
        )
        self.tenant = Tenant.objects.create(
            organization=self.organization,
            user=self.tenant_user,
            first_name='Amina',
            last_name='Otieno',
            phone_number='+254700000010',
        )
        property_record = Property.objects.create(organization=self.organization, name='Acacia')
        building = Building.objects.create(property=property_record, name='Block A')
        self.unit = Unit.objects.create(building=building, name='A-1')
        self.lease = Lease.objects.create(
            tenant=self.tenant,
            unit=self.unit,
            reference='L-1',
            start_date=date(2026, 1, 1),
            monthly_rent_minor=100000,
            status=Lease.Status.ACTIVE,
        )

    def test_emergency_request_is_priority_one_and_lifecycle_notifies(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Burst pipe',
            'description': 'Water everywhere',
            'hazard': 5,
            'vulnerability': 3,
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data['priority_class'], 1)
        self.assertTrue(created.data['emergency_override'])
        self.assertEqual(created.data['unit'], self.unit.pk)
        self.assertEqual(created.data['status'], 'OPEN')
        request_id = created.data['id']

        self.client.force_authenticate(self.accountant)
        denied = self.client.get('/api/v1/maintenance/requests/')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.other_tech)
        hidden = self.client.get('/api/v1/maintenance/requests/')
        self.assertEqual(hidden.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden.data, [])

        self.client.force_authenticate(self.caretaker)
        assigned = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        self.assertEqual(assigned.data['status'], 'IN_PROGRESS')
        self.assertEqual(assigned.data['work_order']['assignee'], self.technician.pk)
        self.assertTrue(Notification.objects.filter(user=self.technician, type='MAINTENANCE_ASSIGNED').exists())

        self.client.force_authenticate(self.technician)
        visible = self.client.get('/api/v1/maintenance/requests/')
        self.assertEqual([row['id'] for row in visible.data], [request_id])
        completed = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {}, format='json')
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(completed.data['status'], 'COMPLETED')
        edited = self.client.patch(
            f'/api/v1/maintenance/requests/{request_id}/',
            {'title': 'Changed'},
            format='json',
        )
        self.assertEqual(edited.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.owner)
        closed = self.client.post(f'/api/v1/maintenance/requests/{request_id}/close/')
        self.assertEqual(closed.status_code, status.HTTP_200_OK)
        self.assertEqual(closed.data['status'], 'CLOSED')
        self.assertTrue(AuditLog.objects.filter(action='maintenance.close', object_id=str(request_id)).exists())
        self.assertTrue(Notification.objects.filter(user=self.tenant_user, type='MAINTENANCE_UPDATED').exists())
        comment = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/comments/',
            {'body': 'Closed after the repair.'},
            format='json',
        )
        self.assertEqual(comment.status_code, status.HTTP_201_CREATED)
        request_row = MaintenanceRequest.objects.get(pk=request_id)
        self.assertEqual(request_row.priority_class, 1)

    def test_match_preview_uses_technician_skills(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/v1/maintenance/match/', {
            'organization': self.organization.pk,
            'jobs': [{
                'job_id': 'job-1',
                'required_skills': ['PLUMBER'],
                'distance_m': 500,
            }],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['assignments'][0]['technician_id'], str(self.technician.pk))
        self.assertEqual(response.data['unmatched_job_ids'], [])
