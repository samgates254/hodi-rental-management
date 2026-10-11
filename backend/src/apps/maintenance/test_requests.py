from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone

from apps.accounts.models import AccountProfile
from apps.audit.models import AuditLog
from apps.leases.models import Lease
from apps.maintenance.models import (
    MaintenanceIssue, MaintenanceRequest, RepairCompletion, TechnicianProfile,
    WorkOrder, WorkOrderAssignment,
)
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
