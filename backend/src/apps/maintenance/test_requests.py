from datetime import date, timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone

from apps.accounts.models import AccountProfile
from apps.audit.models import AuditLog
from apps.billing.models import Charge, Invoice, LedgerPosting, Payment, PaymentAllocation, PaymentReversal
from apps.leases.models import Lease
from apps.maintenance.models import (
    JobMaterialPurchase, JobMaterialReceipt, MaintenanceIssue, MaintenanceRequest,
    RepairCompletion, RepairCompletionEvidence, TechnicianProfile, RepairQuotation,
    RepairQuotationLine, TurnoverAssessment, TurnoverChecklistItem, WorkOrder, WorkOrderAssignment,
)
from apps.marketplace.models import SupplierProfile
from apps.notifications.models import Notification
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.subscriptions.models import SubscriptionInvoice, SubscriptionPayment
from apps.tenants.models import Tenant
from common.rental_dates import rental_business_date


class MaintenanceRequestApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='owner', password='password')
        self.caretaker = user_model.objects.create_user(username='caretaker', password='password')
        self.accountant = user_model.objects.create_user(username='accountant', password='password')
        self.technician = user_model.objects.create_user(username='tech', password='password')
        self.other_tech = user_model.objects.create_user(username='other-tech', password='password')
        self.same_org_other_tech = user_model.objects.create_user(username='same-org-other-tech', password='password')
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
            organization=self.organization, user=self.same_org_other_tech, role=OrganizationMembership.Role.TECHNICIAN,
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

    def _create_request_for_ordering(self, title):
        self.client.force_authenticate(self.tenant_user)
        response = self.client.post('/api/v1/maintenance/requests/', {
            'title': title,
            'description': f'{title} details',
            'hazard': 2,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data['id']

    def _set_request_ordering(self, request_id, *, priority_class, created_at):
        MaintenanceRequest.objects.filter(pk=request_id).update(
            priority_class=priority_class,
            created_at=created_at,
        )

    def _create_direct_request(self, unit, title, assignee=None):
        request = MaintenanceRequest.objects.create(
            unit=unit,
            created_by=self.owner,
            title=title,
            description=f'{title} details',
            hazard=2,
            vulnerability=1,
            priority_class=2,
            score_millis=1000,
        )
        WorkOrder.objects.create(request=request, assignee=assignee)
        return request.pk

    def _create_other_organization_unit(self):
        property_record = Property.objects.create(organization=self.other, name='Other property')
        building = Building.objects.create(property=property_record, name='Other building')
        return Unit.objects.create(building=building, name='Other unit')

    def test_staff_queue_orders_by_priority_oldest_first_and_primary_key(self):
        first_tied = self._create_request_for_ordering('First tied request')
        class_one = self._create_request_for_ordering('Class one request')
        second_tied = self._create_request_for_ordering('Second tied request')
        newer_tie = self._create_request_for_ordering('Newer tied request')
        older_lower_priority = self._create_request_for_ordering('Older lower priority request')
        now = timezone.now()
        tied_created_at = now - timedelta(days=4)
        self._set_request_ordering(first_tied, priority_class=2, created_at=tied_created_at)
        self._set_request_ordering(class_one, priority_class=1, created_at=now)
        self._set_request_ordering(second_tied, priority_class=2, created_at=tied_created_at)
        self._set_request_ordering(newer_tie, priority_class=2, created_at=now - timedelta(days=2))
        self._set_request_ordering(older_lower_priority, priority_class=3, created_at=now - timedelta(days=10))

        self.client.force_authenticate(self.owner)
        response = self.client.get('/api/v1/maintenance/requests/queue/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row['id'] for row in response.data],
            [class_one, first_tied, second_tied, newer_tie, older_lower_priority],
        )

    def test_tenant_history_retains_priority_then_newest_first_ordering(self):
        older_same_priority = self._create_request_for_ordering('Older same priority request')
        newer_same_priority = self._create_request_for_ordering('Newer same priority request')
        older_lower_priority = self._create_request_for_ordering('Older lower priority request')
        now = timezone.now()
        self._set_request_ordering(older_same_priority, priority_class=2, created_at=now - timedelta(days=4))
        self._set_request_ordering(newer_same_priority, priority_class=2, created_at=now - timedelta(days=2))
        self._set_request_ordering(older_lower_priority, priority_class=3, created_at=now - timedelta(days=10))

        self.client.force_authenticate(self.tenant_user)
        response = self.client.get('/api/v1/maintenance/requests/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row['id'] for row in response.data],
            [newer_same_priority, older_same_priority, older_lower_priority],
        )

    def test_tenant_history_excludes_another_tenants_requests(self):
        own_request = self._create_request_for_ordering('Own tenant request')
        other_user = get_user_model().objects.create_user(username='other-tenant-user', password='password')
        other_tenant = Tenant.objects.create(
            organization=self.other,
            user=other_user,
            first_name='Other',
            last_name='Tenant',
            phone_number='+254700000011',
        )
        other_unit = self._create_other_organization_unit()
        other_request = self._create_direct_request(other_unit, 'Another tenant request')
        MaintenanceRequest.objects.filter(pk=other_request).update(tenant=other_tenant)

        self.client.force_authenticate(self.tenant_user)
        response = self.client.get('/api/v1/maintenance/requests/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data], [own_request])

    def test_tenant_history_excludes_records_after_its_organization_is_deactivated(self):
        request_id = self._create_request_for_ordering('Deactivated organization request')
        OrganizationMembership.objects.create(
            organization=self.other,
            user=self.tenant_user,
            role=OrganizationMembership.Role.CARETAKER,
        )
        self.organization.is_active = False
        self.organization.save(update_fields=('is_active', 'updated_at'))

        self.client.force_authenticate(self.tenant_user)
        response = self.client.get('/api/v1/maintenance/requests/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(request_id, [row['id'] for row in response.data])

    def test_tenant_cannot_access_staff_queue_but_can_access_tenant_history(self):
        request_id = self._create_request_for_ordering('Tenant request')

        self.client.force_authenticate(self.tenant_user)
        queue_response = self.client.get('/api/v1/maintenance/requests/queue/')
        history_response = self.client.get('/api/v1/maintenance/requests/')

        self.assertEqual(queue_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(history_response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in history_response.data], [request_id])

    def test_caretaker_can_access_only_their_organization_queue(self):
        own_request = self._create_request_for_ordering('Caretaker organization request')
        other_request = self._create_direct_request(
            self._create_other_organization_unit(),
            'Other organization request',
        )

        self.client.force_authenticate(self.caretaker)
        response = self.client.get('/api/v1/maintenance/requests/queue/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data], [own_request])
        self.assertNotIn(other_request, [row['id'] for row in response.data])

    def test_technician_cannot_access_organization_wide_queue(self):
        self.client.force_authenticate(self.technician)

        response = self.client.get('/api/v1/maintenance/requests/queue/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_technician_visibility_only_returns_requests_assigned_to_them(self):
        assigned_request = self._create_request_for_ordering('Assigned request')
        unassigned_request = self._create_request_for_ordering('Unassigned request')
        another_technician_request = self._create_request_for_ordering('Another technician request')
        self.client.force_authenticate(self.caretaker)
        assignment = self.client.post(
            f'/api/v1/maintenance/requests/{assigned_request}/assign/',
            {'user_id': self.technician.pk},
            format='json',
        )
        self.assertEqual(assignment.status_code, status.HTTP_200_OK, assignment.data)
        WorkOrder.objects.filter(request_id=another_technician_request).update(assignee=self.same_org_other_tech)
        cross_organization_request = self._create_direct_request(
            self._create_other_organization_unit(),
            'Other organization assignment',
            assignee=self.technician,
        )

        self.client.force_authenticate(self.technician)
        response = self.client.get('/api/v1/maintenance/requests/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data], [assigned_request])
        self.assertNotIn(unassigned_request, [row['id'] for row in response.data])
        self.assertNotIn(another_technician_request, [row['id'] for row in response.data])
        self.assertNotIn(cross_organization_request, [row['id'] for row in response.data])
        hidden_detail = self.client.get(f'/api/v1/maintenance/requests/{another_technician_request}/')
        self.assertEqual(hidden_detail.status_code, status.HTTP_404_NOT_FOUND)

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
        legacy_issue = MaintenanceIssue.objects.get(operational_request_id=request_id)
        self.assertEqual(legacy_issue.tenant_id, self.tenant.pk)
        self.assertTrue(WorkOrder.objects.filter(request_id=request_id).exists())

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
        legacy_issue.refresh_from_db()
        self.assertEqual(legacy_issue.status, MaintenanceIssue.Status.IN_PROGRESS)
        self.assertEqual(assigned.data['work_order']['assignee'], self.technician.pk)
        self.assertTrue(Notification.objects.filter(user=self.technician, type='MAINTENANCE_ASSIGNED').exists())
        linked_issue = self.client.get('/api/v1/maintenance/issues/').data[0]
        self.assertEqual(linked_issue['operational_request_id'], request_id)
        self.assertEqual(linked_issue['operational_status'], 'IN_PROGRESS')
        self.assertEqual(linked_issue['status'], 'IN_PROGRESS')

        self.client.force_authenticate(self.technician)
        visible = self.client.get('/api/v1/maintenance/requests/')
        self.assertEqual([row['id'] for row in visible.data], [request_id])
        started = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(started.status_code, status.HTTP_200_OK)
        completion_payload = {
            'diagnosis': 'Valve seal failed', 'failure_category': 'WEAR',
            'resolution_summary': 'Replaced the valve seal and tested the line.',
            'outcome': 'FIXED', 'labour_cost_cents': 2500,
            'materials_cost_cents': 600, 'other_cost_cents': 0,
            'materials': [{'description': 'Valve seal', 'quantity': '1', 'unit': 'piece', 'unit_cost_cents': 600}],
        }
        completed = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/complete/', completion_payload, format='json',
        )
        self.assertEqual(completed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(completed.data['status'], 'SUBMITTED')
        legacy_issue.refresh_from_db()
        self.assertEqual(legacy_issue.status, MaintenanceIssue.Status.IN_PROGRESS)
        self.client.force_authenticate(self.caretaker)
        linked_issue = self.client.get('/api/v1/maintenance/issues/').data[0]
        self.assertEqual(linked_issue['operational_status'], 'COMPLETED')
        self.assertEqual(linked_issue['status'], 'IN_PROGRESS')
        self.client.force_authenticate(self.technician)
        edited = self.client.patch(
            f'/api/v1/maintenance/requests/{request_id}/',
            {'title': 'Changed'},
            format='json',
        )
        self.assertEqual(edited.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.owner)
        verified = self.client.post(f'/api/v1/maintenance/requests/{request_id}/close/', {'notes': 'Tested and verified.'}, format='json')
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertEqual(verified.data['status'], 'VERIFIED')
        self.assertEqual(MaintenanceRequest.objects.get(pk=request_id).status, 'CLOSED')
        legacy_issue.refresh_from_db()
        self.assertEqual(legacy_issue.status, MaintenanceIssue.Status.RESOLVED)
        linked_issue = self.client.get('/api/v1/maintenance/issues/').data[0]
        self.assertEqual(linked_issue['operational_status'], 'CLOSED')
        self.assertEqual(linked_issue['status'], 'RESOLVED')
        self.assertTrue(AuditLog.objects.filter(
            action='maintenance.completion_verified', object_id=str(completed.data['id']),
        ).exists())
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

    def test_match_preview_excludes_unverified_and_profileless_technicians(self):
        unverified = get_user_model().objects.create_user(username='unverified-tech', password='password')
        OrganizationMembership.objects.create(
            organization=self.organization, user=unverified, role=OrganizationMembership.Role.TECHNICIAN,
        )
        TechnicianProfile.objects.create(
            user=unverified, trade='PLUMBER', skills=['PLUMBER'], verified=False, available=True,
            rating_milli=5000, acceptance_milli=1000,
        )
        profileless = get_user_model().objects.create_user(username='profileless-tech', password='password')
        OrganizationMembership.objects.create(
            organization=self.organization, user=profileless, role=OrganizationMembership.Role.TECHNICIAN,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.post('/api/v1/maintenance/match/', {
            'organization': self.organization.pk,
            'jobs': [{'job_id': 'qualified-job', 'required_skills': ['PLUMBER'], 'distance_m': 100}],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['assignments'][0]['technician_id'], str(self.technician.pk))

    def test_unverified_technician_cannot_be_assigned(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Electrical fault', 'description': 'No lights', 'hazard': 2,
        }, format='json')
        profile = TechnicianProfile.objects.get(user=self.technician)
        profile.verified = False
        profile.save(update_fields=('verified', 'updated_at'))
        self.client.force_authenticate(self.caretaker)
        response = self.client.post(
            f"/api/v1/maintenance/requests/{created.data['id']}/assign/",
            {'user_id': self.technician.pk}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WorkOrder.objects.get(request_id=created.data['id']).status, WorkOrder.Status.PENDING)

    def test_quote_approval_completion_and_rejected_verification_are_auditable(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Kitchen leak', 'description': 'Pipe under sink is leaking.', 'hazard': 3,
        }, format='json')
        request_id = created.data['id']

        self.client.force_authenticate(self.caretaker)
        triaged = self.client.post(f'/api/v1/maintenance/requests/{request_id}/triage/', {
            'category': 'PLUMBING', 'hazard': 3, 'vulnerability': 1,
            'notes': 'Check the isolation valve.', 'requires_approval': True,
        }, format='json')
        self.assertEqual(triaged.status_code, status.HTTP_200_OK)
        self.assertTrue(triaged.data['requires_approval'])
        assigned = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.technician)
        blocked = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        quote = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'labour_estimate_cents': 2500, 'materials_estimate_cents': 600,
            'other_estimate_cents': 100, 'explanation': 'Replace washer and test the pipe.',
        }, format='json')
        self.assertEqual(quote.status_code, status.HTTP_201_CREATED)
        self.assertEqual(quote.data['total_estimate_cents'], 3200)

        self.client.force_authenticate(self.technician)
        own_decision = self.client.post(
            f"/api/v1/maintenance/requests/{request_id}/quotations/{quote.data['id']}/decision/",
            {'approved': True}, format='json',
        )
        self.assertEqual(own_decision.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.owner)
        approved_quote = self.client.post(
            f"/api/v1/maintenance/requests/{request_id}/quotations/{quote.data['id']}/decision/",
            {'approved': True, 'notes': 'Approved for the stated scope.'}, format='json',
        )
        self.assertEqual(approved_quote.status_code, status.HTTP_200_OK)
        immutable = self.client.post(
            f"/api/v1/maintenance/requests/{request_id}/quotations/{quote.data['id']}/decision/",
            {'approved': False, 'notes': 'Changing decision.'}, format='json',
        )
        self.assertEqual(immutable.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.technician)
        revision = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'labour_estimate_cents': 2700, 'materials_estimate_cents': 500,
            'other_estimate_cents': 0, 'explanation': 'Revised after inspection.',
        }, format='json')
        self.assertEqual(revision.status_code, status.HTTP_201_CREATED)
        self.assertEqual(revision.data['revision_of'], quote.data['id'])
        self.client.force_authenticate(self.owner)
        rejected_quote = self.client.post(
            f"/api/v1/maintenance/requests/{request_id}/quotations/{revision.data['id']}/decision/",
            {'approved': False, 'notes': 'Clarify material need.'}, format='json',
        )
        self.assertEqual(rejected_quote.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.technician)
        final_quote = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'labour_estimate_cents': 2700, 'materials_estimate_cents': 500,
            'other_estimate_cents': 0, 'explanation': 'Final, clarified estimate.',
        }, format='json')
        self.assertEqual(final_quote.data['revision_of'], revision.data['id'])
        self.client.force_authenticate(self.owner)
        approved_final = self.client.post(
            f"/api/v1/maintenance/requests/{request_id}/quotations/{final_quote.data['id']}/decision/",
            {'approved': True, 'notes': 'Approved.'}, format='json',
        )
        self.assertEqual(approved_final.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.technician)
        started = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(started.status_code, status.HTTP_200_OK)
        submitted = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {
            'diagnosis': 'Washer worn out', 'failure_category': 'WEAR',
            'resolution_summary': 'Replaced washer; no leak under pressure.', 'outcome': 'FIXED',
            'labour_cost_cents': 2500, 'materials_cost_cents': 600, 'other_cost_cents': 0,
            'materials': [{'description': 'Rubber washer', 'quantity': '1', 'unit': 'piece', 'unit_cost_cents': 600}],
        }, format='json')
        self.assertEqual(submitted.status_code, status.HTTP_201_CREATED)
        completion_id = submitted.data['id']

        self.client.force_authenticate(self.technician)
        self_approval = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': completion_id, 'approved': True, 'notes': 'Self approval attempt.',
        }, format='json')
        self.assertEqual(self_approval.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.owner)
        rejected = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': completion_id, 'approved': False, 'notes': 'Please test after replacing the washer.',
        }, format='json')
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)
        self.assertEqual(rejected.data['status'], 'REJECTED')
        request_row = MaintenanceRequest.objects.get(pk=request_id)
        self.assertEqual(request_row.status, MaintenanceRequest.Status.IN_PROGRESS)
        self.assertEqual(request_row.work_order.status, WorkOrder.Status.IN_PROGRESS)

        self.client.force_authenticate(self.technician)
        resubmitted = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {
            'diagnosis': 'Washer replaced', 'failure_category': 'WEAR',
            'resolution_summary': 'Pressure test completed; no leak found.', 'outcome': 'FIXED',
            'labour_cost_cents': 2500, 'materials_cost_cents': 600,
        }, format='json')
        self.assertEqual(resubmitted.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.owner)
        verified = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': resubmitted.data['id'], 'approved': True, 'notes': 'Pressure test verified.',
        }, format='json')
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertEqual(verified.data['status'], 'VERIFIED')
        request_row.refresh_from_db()
        self.assertEqual(request_row.status, MaintenanceRequest.Status.CLOSED)
        self.assertEqual(request_row.work_order.assignments.count(), 1)
        self.assertEqual(request_row.work_order.completions.count(), 2)
        conflicting_verify = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': resubmitted.data['id'], 'approved': False, 'notes': 'Conflicting late rejection.',
        }, format='json')
        self.assertEqual(conflicting_verify.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.filter(action='maintenance.completion_verified').count(), 1)
        self.assertTrue(AuditLog.objects.filter(action='maintenance.quote_submitted').exists())
        self.assertTrue(AuditLog.objects.filter(action='maintenance.quote_approved').exists())
        self.assertTrue(AuditLog.objects.filter(action='maintenance.verification_rejected').exists())
        self.assertTrue(AuditLog.objects.filter(action='maintenance.completion_verified').exists())

        self.client.force_authenticate(self.tenant_user)
        tenant_view = self.client.get(f'/api/v1/maintenance/requests/{request_id}/')
        self.assertEqual(tenant_view.status_code, status.HTTP_200_OK)
        self.assertEqual(tenant_view.data['completion']['outcome'], 'FIXED')
        self.assertIsNone(tenant_view.data['completion']['actual_total_cents'])
        self.assertEqual(tenant_view.data['quotations'][0]['status'], 'APPROVED')
        self.assertEqual(tenant_view.data['triage_notes'], '')

    def _assigned_quote_request(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Broken tap', 'description': 'The kitchen tap leaks.', 'hazard': 2,
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        request_id = created.data['id']
        self.client.force_authenticate(self.caretaker)
        assigned = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.technician)
        return request_id

    def _approved_material_request(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Repair kitchen tap', 'description': 'The tap valve is worn.', 'hazard': 2,
        }, format='json')
        request_id = created.data['id']
        self.client.force_authenticate(self.caretaker)
        triaged = self.client.post(f'/api/v1/maintenance/requests/{request_id}/triage/', {
            'category': 'PLUMBING', 'hazard': 2, 'vulnerability': 1,
            'notes': 'Replace valve.', 'requires_approval': True,
        }, format='json')
        self.assertEqual(triaged.status_code, status.HTTP_200_OK, triaged.data)
        assigned = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_200_OK, assigned.data)
        self.client.force_authenticate(self.technician)
        quote = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Replace valve and install.',
            'lines': [
                {'category': 'MATERIAL', 'description': 'Tap valve', 'quantity': '5', 'unit': 'item', 'unit_price_cents': 100},
                {'category': 'LABOUR', 'description': 'Plumbing labour', 'quantity': '1', 'unit': 'job', 'unit_price_cents': 500},
            ],
        }, format='json')
        self.assertEqual(quote.status_code, status.HTTP_201_CREATED, quote.data)
        self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote.data["id"]}/submit/', {}, format='json',
        )
        self.client.force_authenticate(self.owner)
        approved = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote.data["id"]}/decision/',
            {'approved': True, 'notes': 'Approved exact scope.'}, format='json',
        )
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        line_id = next(line['id'] for line in approved.data['lines'] if line['category'] == 'MATERIAL')
        return request_id, approved.data, line_id

    def _purchase_payload(self, quote, line_id, *, key=None, quantity='2', unit_price_cents=150, overrun_reason=''):
        return {
            'quotation_id': quote['id'], 'quotation_line_id': line_id,
            'supplier_name': 'Rongai Hardware', 'supplier_reference': 'RH-2401',
            'quantity': quantity, 'unit_price_cents': unit_price_cents,
            'purchase_date': '2026-10-12', 'idempotency_key': str(key or uuid4()),
            'overrun_reason': overrun_reason,
        }

    def _financial_table_counts(self):
        return (
            Invoice.objects.count(), Charge.objects.count(), Payment.objects.count(),
            PaymentAllocation.objects.count(), PaymentReversal.objects.count(), LedgerPosting.objects.count(),
            SubscriptionInvoice.objects.count(), SubscriptionPayment.objects.count(),
        )

    def _request_turnover(self, request_id, *, key=None):
        self.client.force_authenticate(self.caretaker)
        return self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/turnover-assessments/',
            {'idempotency_key': str(key or uuid4())}, format='json',
        )

    def _create_and_start_repair(self):
        self.client.force_authenticate(self.caretaker)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'unit': self.unit.pk, 'title': 'Prepare vacant unit',
            'description': 'Repair and inspect before reletting.', 'hazard': 2,
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        request_id = created.data['id']
        assigned = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_200_OK, assigned.data)
        self.client.force_authenticate(self.technician)
        accepted = self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        started = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(started.status_code, status.HTTP_200_OK, started.data)
        return request_id

    def _submit_and_verify_repair(self, request_id):
        self.client.force_authenticate(self.technician)
        started = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(started.status_code, status.HTTP_200_OK, started.data)
        submitted = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {
            'diagnosis': 'Fixture inspection complete', 'failure_category': 'OTHER',
            'resolution_summary': 'Repair completed for verification.', 'outcome': 'FIXED',
            'labour_cost_cents': 100, 'materials_cost_cents': 0, 'other_cost_cents': 0,
        }, format='json')
        self.assertEqual(submitted.status_code, status.HTTP_201_CREATED, submitted.data)
        self.client.force_authenticate(self.owner)
        verified = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': submitted.data['id'], 'approved': True, 'notes': 'Reviewed repair evidence and outcome.',
        }, format='json')
        self.assertEqual(verified.status_code, status.HTTP_200_OK, verified.data)
        return submitted.data['id']

    def _vacate_fixture_lease(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f'/api/v1/leases/{self.lease.pk}/terminate/', {
            'end_date': (rental_business_date() - timedelta(days=1)).isoformat(),
            'reason': 'Unit vacated for turnover.',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_completion_evidence_is_private_idempotent_and_audited(self):
        request_id = self._assigned_quote_request()
        self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        completion = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {
            'diagnosis': 'Seal worn', 'failure_category': 'WEAR',
            'resolution_summary': 'Seal replaced; test passed.', 'outcome': 'FIXED',
            'labour_cost_cents': 100, 'materials_cost_cents': 0,
        }, format='json')
        self.assertEqual(completion.status_code, status.HTTP_201_CREATED, completion.data)
        completion_id = completion.data['id']
        endpoint = f'/api/v1/maintenance/requests/{request_id}/completions/{completion_id}/evidence/'
        payload = {
            'category': 'AFTER_PHOTO', 'caption': 'Seal after replacement.',
            'evidence_reference': 'private-store/repairs/after-image-001',
        }
        finance_before = self._financial_table_counts()

        created = self.client.post(endpoint, payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        evidence = RepairCompletionEvidence.objects.get()
        self.assertEqual(evidence.completion_id, completion_id)
        self.assertEqual(evidence.maintenance_request_id, request_id)
        self.assertEqual(evidence.organization_id, self.organization.pk)
        self.assertEqual(evidence.recorded_by_id, self.technician.pk)
        self.assertEqual(created.data['evidence']['evidence_reference'], payload['evidence_reference'])
        self.assertFalse(created.data['idempotent_replay'])

        repeated = self.client.post(endpoint, payload, format='json')
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertTrue(repeated.data['idempotent_replay'])
        assigned_technician_read = self.client.get(endpoint)
        self.assertEqual(assigned_technician_read.status_code, status.HTTP_200_OK)
        self.assertEqual(len(assigned_technician_read.data), 1)
        conflicting = self.client.post(endpoint, {**payload, 'caption': 'Changed caption.'}, format='json')
        self.assertEqual(conflicting.status_code, status.HTTP_400_BAD_REQUEST)
        public_url = self.client.post(endpoint, {**payload, 'evidence_reference': 'https://example.invalid/private.jpg'}, format='json')
        self.assertEqual(public_url.status_code, status.HTTP_400_BAD_REQUEST)
        wrong_completion = self.client.get(
            f'/api/v1/maintenance/requests/{request_id}/completions/999999/evidence/',
        )
        self.assertEqual(wrong_completion.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.owner)
        staff_read = self.client.get(endpoint)
        self.assertEqual(staff_read.status_code, status.HTTP_200_OK)
        self.assertEqual(len(staff_read.data), 1)
        self.client.force_authenticate(self.tenant_user)
        tenant_read = self.client.get(endpoint)
        self.assertEqual(tenant_read.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.other_tech)
        cross_org_read = self.client.get(endpoint)
        self.assertEqual(cross_org_read.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(AuditLog.objects.filter(action='maintenance.completion_evidence_recorded').count(), 1)
        self.assertEqual(self._financial_table_counts(), finance_before)

    def test_turnover_assessment_requires_vacancy_and_preserves_unit_status(self):
        request_id = self._create_and_start_repair()
        self.unit.status = Unit.Status.AVAILABLE
        self.unit.save(update_fields=('status', 'updated_at'))
        active_lease_with_available_unit = self._request_turnover(request_id)
        self.assertEqual(active_lease_with_available_unit.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('active lease', str(active_lease_with_available_unit.data).lower())
        self.unit.status = Unit.Status.OCCUPIED
        self.unit.save(update_fields=('status', 'updated_at'))
        blocked = self._request_turnover(request_id)
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(TurnoverAssessment.objects.exists())
        self.assertEqual(self.unit.status, Unit.Status.OCCUPIED)

    def test_turnover_failure_reassessment_and_ready_decision_are_audited_without_changing_lease_or_unit(self):
        request_id, _, _ = self._approved_material_request()
        self._vacate_fixture_lease()
        self.unit.refresh_from_db()
        self.unit.status = Unit.Status.MAINTENANCE
        self.unit.save(update_fields=('status', 'updated_at'))
        finance_before = self._financial_table_counts()

        initial = self._request_turnover(request_id)
        self.assertEqual(initial.status_code, status.HTTP_201_CREATED, initial.data)
        assessment_id = initial.data['assessment']['id']
        self.assertEqual(initial.data['assessment']['status'], 'REQUESTED')
        replay = self._request_turnover(request_id, key=uuid4())
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)

        decision_url = f'/api/v1/maintenance/requests/{request_id}/turnover-assessments/{assessment_id}/assess/'
        checklist_pass = [{'item_key': 'fixtures', 'label': 'Fixtures operating', 'passed': True, 'notes': ''}]
        self.client.force_authenticate(self.owner)
        unverified_job = self.client.post(decision_url, {
            'ready': True, 'checklist_items': checklist_pass,
        }, format='json')
        self.assertEqual(unverified_job.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.caretaker)
        unauthorized_ready = self.client.post(decision_url, {
            'ready': True, 'checklist_items': checklist_pass,
        }, format='json')
        self.assertEqual(unauthorized_ready.status_code, status.HTTP_403_FORBIDDEN)
        failed = self.client.post(decision_url, {
            'ready': False, 'outstanding_issues': 'Kitchen tap still leaks.',
            'checklist_items': [{**checklist_pass[0], 'passed': False, 'notes': 'Leak detected.'}],
        }, format='json')
        self.assertEqual(failed.status_code, status.HTTP_201_CREATED, failed.data)
        self.assertEqual(failed.data['assessment']['status'], 'FAILED')
        self.assertEqual(TurnoverChecklistItem.objects.filter(assessment_id=assessment_id).count(), 1)
        same_failure = self.client.post(decision_url, {
            'ready': False, 'outstanding_issues': 'Kitchen tap still leaks.',
            'checklist_items': [{**checklist_pass[0], 'passed': False, 'notes': 'Leak detected.'}],
        }, format='json')
        self.assertEqual(same_failure.status_code, status.HTTP_200_OK)
        self.assertTrue(same_failure.data['idempotent_replay'])
        self.client.force_authenticate(self.owner)
        conflicting = self.client.post(decision_url, {
            'ready': True, 'checklist_items': checklist_pass,
        }, format='json')
        self.assertEqual(conflicting.status_code, status.HTTP_400_BAD_REQUEST)

        reassessment = self._request_turnover(request_id)
        self.assertEqual(reassessment.status_code, status.HTTP_201_CREATED, reassessment.data)
        new_assessment_id = reassessment.data['assessment']['id']
        self.assertEqual(reassessment.data['assessment']['revision_of'], assessment_id)
        self._submit_and_verify_repair(request_id)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, Unit.Status.MAINTENANCE)

        ready_url = f'/api/v1/maintenance/requests/{request_id}/turnover-assessments/{new_assessment_id}/assess/'
        self.client.force_authenticate(self.owner)
        ready = self.client.post(ready_url, {
            'ready': True, 'checklist_items': checklist_pass,
        }, format='json')
        self.assertEqual(ready.status_code, status.HTTP_201_CREATED, ready.data)
        self.assertEqual(ready.data['assessment']['status'], 'READY')
        self.assertEqual(ready.data['assessment']['assessed_by'], self.owner.pk)
        self.assertIsNotNone(ready.data['assessment']['assessed_at'])
        duplicate_ready = self.client.post(ready_url, {
            'ready': True, 'checklist_items': checklist_pass,
        }, format='json')
        self.assertEqual(duplicate_ready.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate_ready.data['idempotent_replay'])
        self.client.force_authenticate(self.caretaker)
        caretaker_ready_replay = self.client.post(ready_url, {
            'ready': True, 'checklist_items': checklist_pass,
        }, format='json')
        self.assertEqual(caretaker_ready_replay.status_code, status.HTTP_403_FORBIDDEN)
        self.unit.refresh_from_db()
        self.lease.refresh_from_db()
        self.assertEqual(self.unit.status, Unit.Status.MAINTENANCE)
        self.assertEqual(self.lease.status, Lease.Status.TERMINATED)
        self.assertEqual(AuditLog.objects.filter(action='maintenance.turnover_inspection_requested').count(), 2)
        self.assertEqual(AuditLog.objects.filter(action='maintenance.turnover_readiness_recorded').count(), 2)
        self.assertEqual(self._financial_table_counts(), finance_before)

        self.client.force_authenticate(self.tenant_user)
        tenant_history = self.client.get(f'/api/v1/maintenance/requests/{request_id}/turnover-assessments/')
        self.assertEqual(tenant_history.status_code, status.HTTP_403_FORBIDDEN)

    def test_verified_ordinary_repair_does_not_create_readiness_or_make_unit_available(self):
        request_id, _, _ = self._approved_material_request()
        self._vacate_fixture_lease()
        self.unit.status = Unit.Status.MAINTENANCE
        self.unit.save(update_fields=('status', 'updated_at'))
        self._submit_and_verify_repair(request_id)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, Unit.Status.MAINTENANCE)
        self.assertFalse(TurnoverAssessment.objects.exists())

    def test_material_purchase_is_scoped_idempotent_and_distinct_from_receipt(self):
        request_id, quote, line_id = self._approved_material_request()
        request_key = uuid4()
        payload = self._purchase_payload(quote, line_id, key=request_key, quantity='1.5', unit_price_cents=101)
        supplier_profile = SupplierProfile.objects.create(organization=self.organization, created_by=self.owner, business_name='Repair Supply Co')
        payload['supplier_profile'] = supplier_profile.pk
        finances_before = self._financial_table_counts()

        self.client.force_authenticate(self.tenant_user)
        tenant_read = self.client.get(f'/api/v1/maintenance/requests/{request_id}/purchases/')
        self.assertEqual(tenant_read.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.technician)
        denied = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', payload, format='json')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.owner)
        created = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        purchase = created.data['purchase']
        self.assertEqual(purchase['purchase_total_cents'], 152)
        self.assertEqual(purchase['status'], 'RECORDED')
        self.assertEqual(purchase['received_quantity'], '0')
        self.assertEqual(purchase['quotation'], quote['id'])
        self.assertEqual(purchase['quotation_line'], line_id)
        self.assertEqual(purchase['supplier_profile'], supplier_profile.pk)
        self.assertEqual(created.data['idempotent_replay'], False)
        comparison = self.client.get('/api/v1/maintenance/price-history/', {'item': 'Tap valve', 'unit': 'item'})
        self.assertEqual(comparison.status_code, status.HTTP_200_OK)
        self.assertEqual(comparison.data[0]['unit_price_cents'], 101)
        self.assertEqual(comparison.data[0]['supplier'], 'Rongai Hardware')

        self.client.force_authenticate(self.technician)
        assigned_job_materials = self.client.get(f'/api/v1/maintenance/requests/{request_id}/purchases/')
        self.assertEqual(assigned_job_materials.status_code, status.HTTP_200_OK)
        self.assertFalse(assigned_job_materials.data['can_record_purchase'])
        self.assertFalse(assigned_job_materials.data['can_acknowledge_receipt'])
        technician_purchase = assigned_job_materials.data['purchases'][0]
        self.assertEqual(technician_purchase['description'], 'Tap valve')
        self.assertEqual(technician_purchase['received_quantity'], '0')
        self.assertEqual(technician_purchase['supplier_name'], '')
        self.assertIsNone(technician_purchase['purchase_total_cents'])
        self.assertEqual(technician_purchase['receipts'], [])

        self.client.force_authenticate(self.owner)
        repeated = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', payload, format='json')
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertTrue(repeated.data['idempotent_replay'])
        self.assertEqual(JobMaterialPurchase.objects.filter(maintenance_request_id=request_id).count(), 1)
        conflict = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', {
            **payload, 'quantity': '1',
        }, format='json')
        self.assertEqual(conflict.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(self.owner)
        self_ack = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase["id"]}/receipts/', {
                'quantity': '1', 'evidence_reference': 'delivery-note-001', 'idempotency_key': str(uuid4()),
            }, format='json',
        )
        self.assertEqual(self_ack.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.technician)
        tech_ack = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase["id"]}/receipts/', {
                'quantity': '1', 'evidence_reference': 'delivery-note-001', 'idempotency_key': str(uuid4()),
            }, format='json',
        )
        self.assertEqual(tech_ack.status_code, status.HTTP_403_FORBIDDEN)

        receipt_key = uuid4()
        self.client.force_authenticate(self.caretaker)
        receipt_payload = {
            'quantity': '1', 'evidence_reference': 'delivery-note-001',
            'idempotency_key': str(receipt_key),
        }
        received = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase["id"]}/receipts/',
            receipt_payload, format='json',
        )
        self.assertEqual(received.status_code, status.HTTP_201_CREATED, received.data)
        self.assertEqual(received.data['purchase']['status'], 'PARTIALLY_RECEIVED')
        self.assertEqual(received.data['purchase']['received_quantity'], '1.000')
        repeated_receipt = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase["id"]}/receipts/',
            receipt_payload, format='json',
        )
        self.assertEqual(repeated_receipt.status_code, status.HTTP_200_OK)
        self.assertTrue(repeated_receipt.data['idempotent_replay'])
        conflict_receipt = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase["id"]}/receipts/', {
                **receipt_payload, 'quantity': '0.5',
            }, format='json',
        )
        self.assertEqual(conflict_receipt.status_code, status.HTTP_400_BAD_REQUEST)
        over_receipt = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase["id"]}/receipts/', {
                'quantity': '1', 'evidence_reference': 'delivery-note-002', 'idempotency_key': str(uuid4()),
            }, format='json',
        )
        self.assertEqual(over_receipt.status_code, status.HTTP_400_BAD_REQUEST)
        final_receipt = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase["id"]}/receipts/', {
                'quantity': '0.5', 'evidence_reference': 'delivery-note-002', 'idempotency_key': str(uuid4()),
            }, format='json',
        )
        self.assertEqual(final_receipt.status_code, status.HTTP_201_CREATED)
        self.assertEqual(final_receipt.data['purchase']['status'], 'RECEIVED')
        self.assertIsNone(final_receipt.data['purchase']['purchase_total_cents'])

        self.client.force_authenticate(self.owner)
        purchase_list = self.client.get(f'/api/v1/maintenance/requests/{request_id}/purchases/')
        self.assertEqual(purchase_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(purchase_list.data['purchases']), 1)
        self.assertEqual(purchase_list.data['purchases'][0]['purchase_total_cents'], 152)
        self.assertTrue(purchase_list.data['can_record_purchase'])
        self.assertEqual(self._financial_table_counts(), finances_before)
        self.assertTrue(AuditLog.objects.filter(action='maintenance.material_purchase_recorded').exists())
        self.assertEqual(AuditLog.objects.filter(action='maintenance.material_receipt_acknowledged').count(), 2)

    def test_purchase_validates_amounts_budget_and_current_approved_revision(self):
        request_id, quote, line_id = self._approved_material_request()
        self.client.force_authenticate(self.owner)
        invalid_price = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', {
            **self._purchase_payload(quote, line_id), 'unit_price_cents': -1,
        }, format='json')
        self.assertEqual(invalid_price.status_code, status.HTTP_400_BAD_REQUEST)
        invalid_quantity = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', {
            **self._purchase_payload(quote, line_id), 'quantity': '0',
        }, format='json')
        self.assertEqual(invalid_quantity.status_code, status.HTTP_400_BAD_REQUEST)
        excess_quantity = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', {
            **self._purchase_payload(quote, line_id), 'quantity': '5.001',
        }, format='json')
        self.assertEqual(excess_quantity.status_code, status.HTTP_400_BAD_REQUEST)

        over_budget_payload = self._purchase_payload(quote, line_id, quantity='5', unit_price_cents=150)
        blocked_overrun = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/', over_budget_payload, format='json',
        )
        self.assertEqual(blocked_overrun.status_code, status.HTTP_400_BAD_REQUEST)
        allowed_overrun = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/', {
                **over_budget_payload, 'overrun_reason': 'Supplier price exceeded the approved material estimate.',
            }, format='json',
        )
        self.assertEqual(allowed_overrun.status_code, status.HTTP_201_CREATED, allowed_overrun.data)
        self.assertEqual(allowed_overrun.data['purchase']['purchase_total_cents'], 750)
        self.assertEqual(allowed_overrun.data['purchase']['overrun_authorized_by'], self.owner.pk)

        self.client.force_authenticate(self.technician)
        pending_revision = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Revision requiring approval.', 'lines': [{
                'category': 'MATERIAL', 'description': 'Tap valve', 'quantity': '5', 'unit': 'item', 'unit_price_cents': 90,
            }],
        }, format='json')
        self.assertEqual(pending_revision.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.owner)
        stale_quote_purchase = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/',
            self._purchase_payload(quote, line_id), format='json',
        )
        self.assertEqual(stale_quote_purchase.status_code, status.HTTP_400_BAD_REQUEST)

    def test_material_cost_summary_links_consumption_without_double_counting_and_requires_overrun_authorization(self):
        request_id, quote, line_id = self._approved_material_request()
        self.client.force_authenticate(self.owner)
        purchase_response = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/',
            self._purchase_payload(quote, line_id, quantity='2', unit_price_cents=150), format='json',
        )
        self.assertEqual(purchase_response.status_code, status.HTTP_201_CREATED, purchase_response.data)
        purchase_id = purchase_response.data['purchase']['id']
        self.client.force_authenticate(self.caretaker)
        receipt_response = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase_id}/receipts/', {
                'quantity': '2', 'evidence_reference': 'goods-received-note-8',
                'idempotency_key': str(uuid4()),
            }, format='json',
        )
        self.assertEqual(receipt_response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.technician)
        accepted = self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        started = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(started.status_code, status.HTTP_200_OK)
        completion = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {
            'diagnosis': 'Valve worn', 'failure_category': 'WEAR',
            'resolution_summary': 'Valve replaced and checked.', 'outcome': 'FIXED',
            'labour_cost_cents': 500, 'materials_cost_cents': 150, 'other_cost_cents': 0,
            'materials': [{
                'description': 'Client supplied wrong label', 'quantity': '1', 'unit': 'unknown',
                'unit_cost_cents': 1, 'purchase_id': purchase_id,
            }],
        }, format='json')
        self.assertEqual(completion.status_code, status.HTTP_201_CREATED, completion.data)
        self.assertEqual(completion.data['materials'][0]['description'], 'Tap valve')
        self.assertEqual(completion.data['materials'][0]['unit'], 'item')
        self.assertEqual(completion.data['materials'][0]['unit_cost_cents'], 150)

        self.client.force_authenticate(self.owner)
        summary = self.client.get(f'/api/v1/maintenance/requests/{request_id}/cost-summary/')
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual(summary.data['approved_total_cents'], 1000)
        self.assertEqual(summary.data['recorded_purchase_total_cents'], 300)
        self.assertEqual(summary.data['reported_material_consumption_cost_cents'], 150)
        self.assertEqual(summary.data['recorded_job_cost_cents'], 800)
        self.assertEqual(summary.data['variance_cents'], -200)
        self.assertEqual(summary.data['supplier_payment_status'], 'NOT_TRACKED')
        self.assertEqual(summary.data['cost_summary_status'], 'PROVISIONAL')
        verified = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': completion.data['id'], 'approved': True, 'notes': 'Costs and work reviewed.',
        }, format='json')
        self.assertEqual(verified.status_code, status.HTTP_200_OK, verified.data)
        summary = self.client.get(f'/api/v1/maintenance/requests/{request_id}/cost-summary/')
        self.assertEqual(summary.data['cost_summary_status'], 'FINAL_RECORDED')
        self.assertTrue(summary.data['materials_reconciled'])

    def test_over_budget_completion_requires_explicit_owner_authorization(self):
        request_id, quote, line_id = self._approved_material_request()
        self.client.force_authenticate(self.owner)
        purchase = self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/', {
            **self._purchase_payload(quote, line_id, quantity='5', unit_price_cents=150),
            'overrun_reason': 'Approved supplier price variance.',
        }, format='json')
        self.assertEqual(purchase.status_code, status.HTTP_201_CREATED, purchase.data)
        purchase_id = purchase.data['purchase']['id']
        self.client.force_authenticate(self.caretaker)
        self.client.post(f'/api/v1/maintenance/requests/{request_id}/purchases/{purchase_id}/receipts/', {
            'quantity': '5', 'evidence_reference': 'delivery-ref-5', 'idempotency_key': str(uuid4()),
        }, format='json')
        self.client.force_authenticate(self.technician)
        self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        completion = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {
            'diagnosis': 'Valve worn', 'failure_category': 'WEAR',
            'resolution_summary': 'Valve replaced.', 'outcome': 'FIXED',
            'labour_cost_cents': 500, 'materials_cost_cents': 0, 'other_cost_cents': 0,
        }, format='json')
        self.assertEqual(completion.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.caretaker)
        unauthorized_overrun = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': completion.data['id'], 'approved': True,
            'authorize_cost_overrun': True, 'cost_overrun_reason': 'Not authorized by this role.',
        }, format='json')
        self.assertEqual(unauthorized_overrun.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.owner)
        missing_reason = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': completion.data['id'], 'approved': True,
        }, format='json')
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        authorized = self.client.post(f'/api/v1/maintenance/requests/{request_id}/verify/', {
            'completion_id': completion.data['id'], 'approved': True,
            'authorize_cost_overrun': True, 'cost_overrun_reason': 'Supplier cost and actual work were reviewed.',
        }, format='json')
        self.assertEqual(authorized.status_code, status.HTTP_200_OK, authorized.data)
        self.assertEqual(authorized.data['cost_overrun_authorized_by_name'], self.owner.username)
        self.assertEqual(authorized.data['cost_overrun_reason'], 'Supplier cost and actual work were reviewed.')

    def test_itemized_quotation_uses_server_totals_rounding_and_immutable_submission(self):
        request_id = self._assigned_quote_request()
        payload = {
            'explanation': 'Replace tap washer and inspect supply line.',
            'lines': [
                {'category': 'LABOUR', 'description': 'Plumbing labour', 'quantity': '1.25', 'unit': 'hour', 'unit_price_cents': 101},
                {'category': 'MATERIAL', 'description': 'Washer', 'quantity': '0.335', 'unit': 'item', 'unit_price_cents': 100},
                {'category': 'TRANSPORT', 'description': 'Travel', 'quantity': '1', 'unit': 'job', 'unit_price_cents': 50},
            ],
        }
        before = (
            RepairQuotation.objects.count(), RepairQuotationLine.objects.count(),
            Invoice.objects.count(), Charge.objects.count(), Payment.objects.count(),
            PaymentAllocation.objects.count(), PaymentReversal.objects.count(), LedgerPosting.objects.count(),
            SubscriptionInvoice.objects.count(), SubscriptionPayment.objects.count(),
        )
        created = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data['status'], 'DRAFT')
        self.assertEqual(created.data['labour_estimate_cents'], 126)
        self.assertEqual(created.data['materials_estimate_cents'], 34)
        self.assertEqual(created.data['other_estimate_cents'], 50)
        self.assertEqual(created.data['total_estimate_cents'], 210)
        self.assertEqual([line['line_total_cents'] for line in created.data['lines']], [126, 34, 50])
        self.assertEqual(RepairQuotation.objects.count(), before[0] + 1)
        self.assertEqual(RepairQuotationLine.objects.count(), before[1] + 3)

        bad_total = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            **payload, 'total_estimate_cents': 999,
        }, format='json')
        self.assertEqual(bad_total.status_code, status.HTTP_400_BAD_REQUEST)
        mismatched_line_total = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Tampered line total.', 'lines': [{
                'category': 'MATERIAL', 'description': 'Washer', 'quantity': '1', 'unit': 'item',
                'unit_price_cents': 100, 'line_total_cents': 1,
            }],
        }, format='json')
        self.assertEqual(mismatched_line_total.status_code, status.HTTP_400_BAD_REQUEST)
        mismatched_subtotal = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            **payload, 'labour_estimate_cents': 127,
        }, format='json')
        self.assertEqual(mismatched_subtotal.status_code, status.HTTP_400_BAD_REQUEST)
        bad_qty = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Invalid quantity.', 'lines': [{
                'category': 'MATERIAL', 'description': 'Washer', 'quantity': '-1', 'unit': 'item', 'unit_price_cents': 100,
            }],
        }, format='json')
        self.assertEqual(bad_qty.status_code, status.HTTP_400_BAD_REQUEST)
        overflow = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Out of range.', 'lines': [{
                'category': 'OTHER', 'description': 'Overflow', 'quantity': '999999999.999',
                'unit': 'job', 'unit_price_cents': 9223372036854775807,
            }],
        }, format='json')
        self.assertEqual(overflow.status_code, status.HTTP_400_BAD_REQUEST)

        estimate_overflow = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/', {
                'explanation': 'Estimate exceeds signed storage range.',
                'labour_estimate_cents': 1 << 63,
                'materials_estimate_cents': 0,
            }, format='json',
        )
        self.assertEqual(estimate_overflow.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('labour_estimate_cents', estimate_overflow.data)

        unit_price_overflow = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/', {
                'explanation': 'Unit price exceeds signed storage range.',
                'lines': [{
                    'category': 'OTHER', 'description': 'Overflow', 'quantity': '1',
                    'unit': 'job', 'unit_price_cents': 1 << 63,
                }],
            }, format='json',
        )
        self.assertEqual(unit_price_overflow.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('unit_price_cents', str(unit_price_overflow.data))

        quote_id = created.data['id']
        changed = self.client.patch(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote_id}/', {
                'explanation': 'Updated estimate after inspection.',
                'lines': [payload['lines'][0]],
            }, format='json',
        )
        self.assertEqual(changed.status_code, status.HTTP_200_OK, changed.data)
        self.assertEqual(changed.data['total_estimate_cents'], 126)
        locked_line_values = list(RepairQuotationLine.objects.filter(quotation_id=created.data['id']).values_list(
            'category', 'description', 'quantity', 'unit', 'unit_price_cents', 'line_total_cents',
        ))
        submitted = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote_id}/submit/', {}, format='json',
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        repeated = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote_id}/submit/', {}, format='json',
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        locked = self.client.patch(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote_id}/', payload, format='json',
        )
        self.assertEqual(locked.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.owner)
        approved = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote_id}/decision/',
            {'approved': True, 'notes': 'Approved for the submitted scope.'}, format='json',
        )
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        approved_line_values = list(RepairQuotationLine.objects.filter(quotation_id=quote_id).values_list(
            'category', 'description', 'quantity', 'unit', 'unit_price_cents', 'line_total_cents',
        ))
        self.assertEqual(approved_line_values, locked_line_values)
        approved_edit = self.client.patch(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote_id}/', payload, format='json',
        )
        self.assertEqual(approved_edit.status_code, status.HTTP_400_BAD_REQUEST)
        after = (
            RepairQuotation.objects.count(), RepairQuotationLine.objects.count(),
            Invoice.objects.count(), Charge.objects.count(), Payment.objects.count(),
            PaymentAllocation.objects.count(), PaymentReversal.objects.count(), LedgerPosting.objects.count(),
            SubscriptionInvoice.objects.count(), SubscriptionPayment.objects.count(),
        )
        self.assertEqual(after[2:], before[2:])
        self.assertEqual(approved_line_values[0][1], 'Plumbing labour')
        self.assertTrue(AuditLog.objects.filter(action='maintenance.quote_draft_created', object_id=str(quote_id)).exists())
        self.assertTrue(AuditLog.objects.filter(action='maintenance.quote_draft_updated', object_id=str(quote_id)).exists())
        self.assertEqual(AuditLog.objects.filter(action='maintenance.quote_submitted', object_id=str(quote_id)).count(), 1)

    def test_legacy_quotation_remains_readable_without_synthetic_lines(self):
        request_id = self._assigned_quote_request()
        created = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'labour_estimate_cents': 1200, 'materials_estimate_cents': 300,
            'other_estimate_cents': 50, 'explanation': 'Existing aggregate estimate.',
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data['total_estimate_cents'], 1550)
        self.assertFalse(created.data['has_itemized_lines'])
        self.assertEqual(created.data['lines'], [])

    def test_rejected_itemized_quotation_resubmits_as_a_linked_revision(self):
        request_id = self._assigned_quote_request()
        payload = {
            'explanation': 'Initial itemized scope.',
            'lines': [{'category': 'MATERIAL', 'description': 'Valve', 'quantity': '1', 'unit': 'item', 'unit_price_cents': 500}],
        }
        first = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{first.data["id"]}/submit/', {}, format='json',
        )
        self.client.force_authenticate(self.owner)
        rejected = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{first.data["id"]}/decision/',
            {'approved': False, 'notes': 'Provide a labour breakdown.'}, format='json',
        )
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.technician)
        revised = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Revised itemized scope.',
            'lines': [
                {'category': 'MATERIAL', 'description': 'Valve', 'quantity': '1', 'unit': 'item', 'unit_price_cents': 500},
                {'category': 'LABOUR', 'description': 'Installation', 'quantity': '1', 'unit': 'job', 'unit_price_cents': 800},
            ],
        }, format='json')
        self.assertEqual(revised.status_code, status.HTTP_201_CREATED)
        self.assertEqual(revised.data['revision_of'], first.data['id'])
        self.assertEqual(revised.data['status'], 'DRAFT')

    def test_quotation_lines_and_decisions_remain_organisation_scoped(self):
        request_id = self._assigned_quote_request()
        created = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Pipe repair.', 'lines': [{
                'category': 'LABOUR', 'description': 'Labour', 'quantity': '1', 'unit': 'job', 'unit_price_cents': 1000,
            }],
        }, format='json')
        quote_id = created.data['id']
        self.client.force_authenticate(self.tenant_user)
        tenant_write = self.client.post(f'/api/v1/maintenance/requests/{request_id}/quotations/', {
            'explanation': 'Tenant should not submit a quotation.', 'lines': [{
                'category': 'MATERIAL', 'description': 'Part', 'quantity': '1', 'unit': 'item', 'unit_price_cents': 100,
            }],
        }, format='json')
        self.assertEqual(tenant_write.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.other_tech)
        response = self.client.patch(
            f'/api/v1/maintenance/requests/{request_id}/quotations/{quote_id}/', {
                'explanation': 'Attempted cross-organisation edit.', 'lines': created.data['lines'],
            }, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_technician_matching_enforces_trade_in_assignment_path(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Electrical fault', 'description': 'Socket sparks.', 'hazard': 3,
        }, format='json')
        request_id = created.data['id']
        self.client.force_authenticate(self.caretaker)
        self.client.post(f'/api/v1/maintenance/requests/{request_id}/triage/', {
            'category': 'ELECTRICAL', 'hazard': 3, 'vulnerability': 1,
        }, format='json')
        denied = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(WorkOrder.objects.get(request_id=request_id).assignee_id)

    def test_assigned_technician_loses_request_access_when_membership_is_revoked(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Leaking pipe', 'description': 'Water under the sink.', 'hazard': 2,
            'category': 'PLUMBING',
        }, format='json')
        request_id = created.data['id']
        self.client.force_authenticate(self.caretaker)
        assigned = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)

        OrganizationMembership.objects.filter(
            organization=self.organization, user=self.technician,
        ).update(is_active=False)
        self.client.force_authenticate(self.technician)
        hidden = self.client.get(f'/api/v1/maintenance/requests/{request_id}/')
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def _report_and_assign(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Blocked drain', 'description': 'Kitchen drain is blocked.',
            'hazard': 2, 'category': 'PLUMBING',
        }, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.caretaker)
        assigned = self.client.post(f"/api/v1/maintenance/requests/{created.data['id']}/assign/", {
            'user_id': self.technician.pk,
        }, format='json')
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        return created.data['id']

    def test_technician_acceptance_is_idempotent_and_only_current_technician_can_respond(self):
        request_id = self._report_and_assign()
        unassigned = get_user_model().objects.create_user(username='unassigned-tech', password='password')
        OrganizationMembership.objects.create(
            organization=self.organization, user=unassigned, role=OrganizationMembership.Role.TECHNICIAN,
        )
        TechnicianProfile.objects.create(user=unassigned, trade='PLUMBER', skills=['PLUMBER'])
        self.client.force_authenticate(unassigned)
        unassigned_response = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json',
        )
        self.assertEqual(unassigned_response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.other_tech)
        hidden = self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.technician)
        accepted = self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        repeated = self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(accepted.data['assignment_status'], WorkOrderAssignment.Status.ACCEPTED)
        self.assertIsNotNone(accepted.data['assignment_responded_at'])
        assignment = WorkOrderAssignment.objects.get(work_order__request_id=request_id)
        self.assertEqual(assignment.status, WorkOrderAssignment.Status.ACCEPTED)
        self.assertEqual(AuditLog.objects.filter(action='maintenance.assignment_accepted').count(), 1)

        declined_after_accept = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/decline/', {'reason': 'Changed plans.'}, format='json',
        )
        self.assertEqual(declined_after_accept.status_code, status.HTTP_400_BAD_REQUEST)

    def test_decline_requires_reason_returns_work_to_queue_and_old_assignee_cannot_respond_after_reassignment(self):
        replacement = get_user_model().objects.create_user(username='replacement-tech', password='password')
        OrganizationMembership.objects.create(
            organization=self.organization, user=replacement, role=OrganizationMembership.Role.TECHNICIAN,
        )
        TechnicianProfile.objects.create(user=replacement, trade='PLUMBER', skills=['PLUMBER'])
        request_id = self._report_and_assign()
        self.client.force_authenticate(self.technician)
        missing_reason = self.client.post(f'/api/v1/maintenance/requests/{request_id}/decline/', {}, format='json')
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        declined = self.client.post(f'/api/v1/maintenance/requests/{request_id}/decline/', {
            'reason': 'Unavailable during the requested window.',
        }, format='json')
        self.assertEqual(declined.status_code, status.HTTP_200_OK)
        assignment = WorkOrderAssignment.objects.get(work_order__request_id=request_id)
        self.assertEqual(assignment.status, WorkOrderAssignment.Status.DECLINED)
        self.assertEqual(assignment.decline_reason, 'Unavailable during the requested window.')
        self.assertIsNotNone(assignment.responded_at)
        self.assertEqual(MaintenanceRequest.objects.get(pk=request_id).status, MaintenanceRequest.Status.OPEN)
        self.assertIsNone(WorkOrder.objects.get(request_id=request_id).assignee_id)

        self.client.force_authenticate(self.caretaker)
        reassigned = self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': replacement.pk,
        }, format='json')
        self.assertEqual(reassigned.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.technician)
        stale_accept = self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        stale_decline = self.client.post(f'/api/v1/maintenance/requests/{request_id}/decline/', {
            'reason': 'Old assignment.',
        }, format='json')
        self.assertEqual(stale_accept.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(stale_decline.status_code, status.HTTP_404_NOT_FOUND)

    def test_follow_up_is_scheduled_audited_and_does_not_allow_unresolved_repair_to_close(self):
        request_id = self._report_and_assign()
        self.client.force_authenticate(self.technician)
        accepted = self.client.post(f'/api/v1/maintenance/requests/{request_id}/accept/', {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        started = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(started.status_code, status.HTTP_200_OK)
        completed = self.client.post(f'/api/v1/maintenance/requests/{request_id}/complete/', {
            'diagnosis': 'Drain obstruction remains beyond the trap.',
            'failure_category': 'BLOCKAGE',
            'resolution_summary': 'Initial clearing attempted; further inspection is required.',
            'outcome': RepairCompletion.Outcome.NEEDS_FOLLOW_UP,
            'follow_up_reason': 'Return with a drain camera.',
            'labour_cost_cents': 1200, 'materials_cost_cents': 0,
        }, format='json')
        self.assertEqual(completed.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.owner)
        cannot_close = self.client.post(f'/api/v1/maintenance/requests/{request_id}/close/', {}, format='json')
        self.assertEqual(cannot_close.status_code, status.HTTP_400_BAD_REQUEST)
        when = timezone.now() + timedelta(days=2)
        payload = {
            'follow_up_at': when.isoformat(), 'reason': 'Inspect the pipe with a drain camera.',
            'assignee_id': self.technician.pk,
        }
        self.client.force_authenticate(self.tenant_user)
        unauthorized = self.client.post(f'/api/v1/maintenance/requests/{request_id}/follow-up/', payload, format='json')
        self.assertEqual(unauthorized.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.caretaker)
        wrong_org_assignee = {**payload, 'assignee_id': self.other_tech.pk}
        wrong_org = self.client.post(
            f'/api/v1/maintenance/requests/{request_id}/follow-up/', wrong_org_assignee, format='json',
        )
        self.assertEqual(wrong_org.status_code, status.HTTP_400_BAD_REQUEST)
        scheduled = self.client.post(f'/api/v1/maintenance/requests/{request_id}/follow-up/', payload, format='json')
        duplicate = self.client.post(f'/api/v1/maintenance/requests/{request_id}/follow-up/', payload, format='json')
        self.assertEqual(scheduled.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(scheduled.data['follow_up_at'])
        self.assertEqual(scheduled.data['follow_up_reason'], payload['reason'])
        self.assertEqual(scheduled.data['follow_up_assignee_name'], 'tech')
        self.assertEqual(AuditLog.objects.filter(action='maintenance.follow_up_scheduled').count(), 1)

        self.client.force_authenticate(self.tenant_user)
        tenant_view = self.client.get(f'/api/v1/maintenance/requests/{request_id}/')
        self.assertEqual(tenant_view.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(tenant_view.data['follow_up_at'])
        self.assertIsNone(tenant_view.data['follow_up_assignee_name'])

    def test_safety_override_is_attributed_and_is_explicit_approval_exception(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Burst pipe', 'description': 'Water escaping rapidly.', 'hazard': 4,
        }, format='json')
        request_id = created.data['id']
        self.client.force_authenticate(self.caretaker)
        missing_reason = self.client.post(f'/api/v1/maintenance/requests/{request_id}/triage/', {
            'category': 'PLUMBING', 'hazard': 4, 'vulnerability': 1,
            'safety_override': True, 'requires_approval': True,
        }, format='json')
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        triaged = self.client.post(f'/api/v1/maintenance/requests/{request_id}/triage/', {
            'category': 'PLUMBING', 'hazard': 4, 'vulnerability': 1,
            'safety_override': True, 'safety_override_reason': 'Stop active water damage.',
            'requires_approval': True,
        }, format='json')
        self.assertEqual(triaged.status_code, status.HTTP_200_OK)
        self.assertTrue(MaintenanceRequest.objects.get(pk=request_id).safety_override)
        self.assertEqual(MaintenanceRequest.objects.get(pk=request_id).safety_override_by_id, self.caretaker.pk)
        triage_audit = AuditLog.objects.get(action='maintenance.triage', object_id=str(request_id))
        self.assertEqual(triage_audit.actor_id, self.caretaker.pk)
        self.client.post(f'/api/v1/maintenance/requests/{request_id}/assign/', {
            'user_id': self.technician.pk,
        }, format='json')
        self.client.force_authenticate(self.technician)
        started = self.client.post(f'/api/v1/maintenance/requests/{request_id}/start/', {}, format='json')
        self.assertEqual(started.status_code, status.HTTP_200_OK)

    def test_edit_updates_linked_legacy_issue_and_records_history(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Leaking tap', 'description': 'Kitchen sink leak', 'hazard': 2,
        }, format='json')
        request_id = created.data['id']
        issue = MaintenanceIssue.objects.get(operational_request_id=request_id)
        self.client.force_authenticate(self.caretaker)
        updated = self.client.patch(f'/api/v1/maintenance/requests/{request_id}/', {
            'title': 'Urgent kitchen leak', 'description': 'Water is reaching the cabinet.', 'hazard': 4,
        }, format='json')
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        issue.refresh_from_db()
        self.assertEqual(issue.title, updated.data['title'])
        self.assertEqual(issue.description, updated.data['description'])
        self.assertEqual(issue.priority, MaintenanceIssue.Priority.HIGH)
        self.assertTrue(issue.updates.filter(note__startswith='Request details updated:').exists())
        self.assertTrue(AuditLog.objects.filter(
            action='maintenance.update', object_id=str(request_id),
        ).exists())

    def test_edit_does_not_rewrite_unlinked_historical_issue(self):
        self.client.force_authenticate(self.tenant_user)
        created = self.client.post('/api/v1/maintenance/requests/', {
            'title': 'Old wiring', 'description': 'Switch sparks', 'hazard': 3,
        }, format='json')
        issue = MaintenanceIssue.objects.get(operational_request_id=created.data['id'])
        issue.operational_request = None
        issue.save(update_fields=('operational_request', 'updated_at'))
        self.client.force_authenticate(self.caretaker)
        updated = self.client.patch(f"/api/v1/maintenance/requests/{created.data['id']}/", {
            'title': 'Repaired wiring note',
        }, format='json')
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        issue.refresh_from_db()
        self.assertEqual(issue.title, 'Old wiring')
