from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import DocumentStatus, Invoice as RentInvoice
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
from apps.tenants.models import Tenant
from apps.audit.models import AuditLog
from .models import OrganizationSubscription, SubscriptionInvoice, SubscriptionPayment, SubscriptionPaymentAttempt, SubscriptionPlan


class SubscriptionApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='subscription-owner', password='test-password')
        self.manager = user_model.objects.create_user(username='subscription-manager', password='test-password')
        self.other_owner = user_model.objects.create_user(username='other-sub-owner', password='test-password')
        self.admin = user_model.objects.create_user(username='hodi-admin', password='test-password', is_staff=True)
        self.organization = Organization.objects.create(name='Subscription Test Org')
        self.other_organization = Organization.objects.create(name='Other Subscription Org')
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.owner, role=OrganizationMembership.Role.OWNER,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.manager, role=OrganizationMembership.Role.PROPERTY_MANAGER,
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization, user=self.other_owner, role=OrganizationMembership.Role.OWNER,
        )
        self.subscription = OrganizationSubscription.objects.get(organization=self.organization)
        self.property = Property.objects.create(organization=self.organization, name='Units Test Property')
        self.building = Building.objects.create(property=self.property, name='Block A')

    def test_catalogue_is_backend_owned_and_prices_are_integer_minor_units(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse('subscriptions:plans'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        plans = {plan['code']: plan for plan in response.data}
        self.assertEqual(plans['free']['price_minor'], 0)
        self.assertEqual(plans['free']['unit_limit'], 5)
        self.assertEqual(plans['starter']['price_minor'], 99_900)
        self.assertEqual(plans['starter']['setup_fee_minor'], 0)
        self.assertEqual(plans['growth']['unit_limit'], 75)
        self.assertEqual(plans['professional']['unit_limit'], 200)
        self.assertTrue(plans['enterprise']['is_custom_pricing'])
        self.assertIsNone(plans['enterprise']['price_minor'])

    def test_active_public_catalogue_is_available_without_auth_and_excludes_internal_fields(self):
        SubscriptionPlan.objects.create(
            code='retired', name='Retired plan', price_minor=1, unit_limit=1,
            is_active=False,
        )
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('subscriptions:plans'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data)
        self.assertNotIn('id', response.data[0])
        self.assertNotIn('version', response.data[0])
        self.assertTrue(all('organization' not in plan for plan in response.data))
        self.assertNotIn('retired', {plan['code'] for plan in response.data})

    def test_free_subscription_is_created_and_other_organization_isolation_is_enforced(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse('subscriptions:organization-subscription'), {'organization': self.organization.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], OrganizationSubscription.Status.FREE)
        self.assertEqual(response.data['effective_unit_limit'], 5)
        self.assertEqual(response.data['unit_count'], 0)
        self.assertEqual(response.data['remaining_units'], 5)
        self.assertFalse(SubscriptionInvoice.objects.filter(organization=self.organization).exists())
        hidden = self.client.get(reverse('subscriptions:organization-subscription'), {'organization': self.other_organization.pk})
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_empty_organization_deletion_removes_only_its_free_subscription(self):
        empty = Organization.objects.create(name='Empty removable organization')
        OrganizationMembership.objects.create(
            organization=empty, user=self.owner, role=OrganizationMembership.Role.OWNER,
        )
        self.client.force_authenticate(self.owner)
        response = self.client.delete(reverse('organizations:organization-detail', args=(empty.pk,)))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Organization.objects.filter(pk=empty.pk).exists())
        self.assertFalse(OrganizationSubscription.objects.filter(organization_id=empty.pk).exists())

    def test_organization_with_subscription_invoice_history_cannot_be_deleted(self):
        self.client.force_authenticate(self.owner)
        self.client.post(reverse('subscriptions:organization-subscription'), {
            'organization': self.organization.pk, 'plan': 'starter',
        }, format='json')
        response = self.client.delete(reverse('organizations:organization-detail', args=(self.organization.pk,)))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Organization.objects.filter(pk=self.organization.pk).exists())
        self.assertTrue(OrganizationSubscription.objects.filter(organization=self.organization).exists())

    def test_client_cannot_change_price_or_select_custom_enterprise_plan(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter', 'price_minor': 1, 'entitlements': {'billing': False}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['amount_minor'], 99_900)
        self.assertEqual(response.data['plan_name'], 'Starter')
        self.assertEqual(response.data['currency'], 'KES')
        self.assertEqual(response.data['monthly_fee_minor'], 99_900)
        self.assertEqual(response.data['setup_fee_minor'], 0)
        self.assertEqual(response.data['amount_paid_minor'], 0)
        self.assertEqual(response.data['outstanding_minor'], 99_900)
        self.assertEqual(response.data['period_start'], timezone.localdate().isoformat())
        self.assertGreater(response.data['period_end'], response.data['period_start'])
        self.assertEqual(response.data['status'], SubscriptionInvoice.Status.ISSUED)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan.code, 'free')
        self.assertEqual(self.subscription.pending_plan.code, 'starter')
        rejected = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'enterprise'}, format='json',
        )
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)

    def test_first_paid_invoice_snapshots_one_time_setup_fee_and_later_months_do_not_repeat_it(self):
        SubscriptionPlan.objects.filter(code='starter').update(setup_fee_minor=15_000)
        self.client.force_authenticate(self.owner)
        first = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data['monthly_fee_minor'], 99_900)
        self.assertEqual(first.data['setup_fee_minor'], 15_000)
        self.assertEqual(first.data['amount_minor'], 114_900)
        self.assertEqual(first.data['outstanding_minor'], 114_900)
        self.assertEqual(first.data['amount_paid_minor'], 0)

        report = self.client.post(
            reverse('subscriptions:report-payment', args=(first.data['id'],)),
            {'reference': 'SETUP-FEE-VERIFIED-1'}, format='json',
        )
        self.client.force_authenticate(self.admin)
        confirmed = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(report.data['id'], 'confirm')),
            {'reason': 'Matched to the verified subscription receipt'}, format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['amount_minor'], 114_900)
        self.assertEqual(SubscriptionPayment.objects.get().amount_minor, 114_900)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.setup_fee_paid)
        self.assertTrue(self.subscription.setup_fee_invoiced)
        self.client.force_authenticate(self.owner)
        invoice_response = self.client.get(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk},
        )
        invoice_view = invoice_response.data['invoices'][0]
        self.assertEqual(invoice_view['amount_paid_minor'], 114_900)
        self.assertEqual(invoice_view['outstanding_minor'], 0)

        # A renewal after the current period does not repeat the fee.
        OrganizationSubscription.objects.filter(pk=self.subscription.pk).update(
            current_period_end=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_authenticate(self.owner)
        renewal = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(renewal.status_code, status.HTTP_201_CREATED)
        self.assertEqual(renewal.data['monthly_fee_minor'], 99_900)
        self.assertEqual(renewal.data['setup_fee_minor'], 0)
        self.assertEqual(renewal.data['amount_minor'], 99_900)

    def test_setup_fee_is_not_repeated_or_repriced_by_duplicate_or_failed_requests(self):
        SubscriptionPlan.objects.filter(code='starter').update(setup_fee_minor=12_500)
        self.client.force_authenticate(self.owner)
        issued = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(issued.data['setup_fee_minor'], 12_500)
        duplicate = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SubscriptionInvoice.objects.filter(organization=self.organization).count(), 1)

        report = self.client.post(
            reverse('subscriptions:report-payment', args=(issued.data['id'],)),
            {'reference': 'SETUP-FEE-REJECT-1'}, format='json',
        )
        self.client.force_authenticate(self.admin)
        rejected = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(report.data['id'], 'reject')),
            {'reason': 'The reference could not be independently verified'}, format='json',
        )
        self.assertEqual(rejected.status_code, status.HTTP_200_OK)
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.setup_fee_paid)
        self.assertTrue(self.subscription.setup_fee_invoiced)
        self.assertEqual(SubscriptionPayment.objects.count(), 0)
        invoice = SubscriptionInvoice.objects.get(pk=issued.data['id'])
        self.assertEqual(invoice.setup_fee_minor, 12_500)
        self.assertEqual(invoice.amount_minor, 112_400)

    def test_existing_subscriptions_are_grandfathered_from_new_setup_fees(self):
        SubscriptionPlan.objects.filter(code='starter').update(setup_fee_minor=50_000)
        self.subscription.setup_fee_invoiced = True
        self.subscription.save(update_fields=('setup_fee_invoiced',))
        self.client.force_authenticate(self.owner)
        issued = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)
        self.assertEqual(issued.data['setup_fee_minor'], 0)
        self.assertEqual(issued.data['amount_minor'], 99_900)

    def test_payment_report_never_activates_plan_until_staff_verification(self):
        SubscriptionPlan.objects.filter(code='starter').update(setup_fee_minor=10_000)
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        invoice_id = created.data['id']
        reported = self.client.post(
            reverse('subscriptions:report-payment', args=(invoice_id,)),
            {'reference': 'QWE123PAYMENT'}, format='json',
        )
        self.assertEqual(reported.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(reported.data['status'], SubscriptionPaymentAttempt.Status.PENDING_REVIEW)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, OrganizationSubscription.Status.FREE)
        self.assertEqual(self.subscription.plan.code, 'free')
        self.assertFalse(self.subscription.setup_fee_paid)
        self.assertTrue(self.subscription.setup_fee_invoiced)
        self.assertEqual(RentInvoice.objects.count(), 0)
        self.assertEqual(SubscriptionPayment.objects.count(), 0)
        self.client.force_authenticate(self.admin)
        missing_reason = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(reported.data['id'], 'confirm')),
            {}, format='json',
        )
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SubscriptionPayment.objects.count(), 0)

        self.client.force_authenticate(self.owner)
        denied = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(reported.data['id'], 'confirm')),
            {'reason': 'A claimed payment reference'}, format='json',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        confirmed = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(reported.data['id'], 'confirm')),
            {'reason': 'Matched independently to the provider statement'}, format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, OrganizationSubscription.Status.ACTIVE)
        self.assertEqual(self.subscription.plan.code, 'starter')
        self.assertEqual(SubscriptionPayment.objects.filter(status=SubscriptionPayment.Status.VERIFIED).count(), 1)
        payment = SubscriptionPayment.objects.get()
        self.assertEqual(payment.verification_reason, 'Matched independently to the provider statement')
        self.assertTrue(AuditLog.objects.filter(
            action='subscription.payment_verified', object_id=str(payment.pk),
            organization=self.organization,
            metadata__reason='Matched independently to the provider statement',
        ).exists())
        self.assertEqual(RentInvoice.objects.count(), 0)
        duplicate = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(reported.data['id'], 'confirm')),
            {'reason': 'Duplicate confirmation attempt'}, format='json',
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_customer_can_report_only_own_organization_invoice(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.client.force_authenticate(self.other_owner)
        response = self.client.post(
            reverse('subscriptions:report-payment', args=(created.data['id'],)),
            {'reference': 'WRONGORG'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(SubscriptionPaymentAttempt.objects.count(), 0)

    def test_revenue_dashboard_requires_hodi_admin_and_counts_confirmed_separate_payments(self):
        url = reverse('subscriptions:admin-revenue')
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['collected_minor'], 0)
        self.assertEqual(RentInvoice.objects.count(), 0)
        self.assertEqual(response.data['free_organizations'], 2)

    def test_unit_limit_blocks_api_creation_and_keeps_existing_records_readable(self):
        for index in range(5):
            Unit.objects.create(building=self.building, name=f'Unit {index + 1}')
        self.client.force_authenticate(self.owner)
        blocked = self.client.post(
            reverse('properties:unit-list'),
            {'building': self.building.pk, 'name': 'Unit 6', 'status': Unit.Status.AVAILABLE}, format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(blocked.data['code'], 'UNIT_LIMIT_REACHED')
        existing = self.client.get(reverse('properties:unit-list'))
        self.assertEqual(existing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(existing.data), 5)
        subscription = self.client.get(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk},
        )
        self.assertEqual(subscription.data['unit_count'], 5)
        self.assertEqual(subscription.data['remaining_units'], 0)

    def test_inactive_units_do_not_count_until_activated(self):
        for index in range(5):
            Unit.objects.create(building=self.building, name=f'Unit {index + 1}')
        inactive = Unit.objects.create(building=self.building, name='Archive', status=Unit.Status.INACTIVE)
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            reverse('properties:unit-detail', args=(inactive.pk,)),
            {'status': Unit.Status.AVAILABLE}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        inactive.refresh_from_db()
        self.assertEqual(inactive.status, Unit.Status.INACTIVE)

    def test_plan_terms_are_immutable_and_must_be_versioned(self):
        plan = SubscriptionPlan.objects.get(code='starter')
        plan.setup_fee_minor = 1
        with self.assertRaises(DjangoValidationError):
            plan.save()

    def test_enterprise_quote_is_staff_configured_and_limit_activates_after_verification(self):
        url = reverse('subscriptions:admin-enterprise-invoice')
        self.client.force_authenticate(self.owner)
        denied = self.client.post(url, {
            'organization': self.organization.pk, 'amount_minor': 7_500_000,
            'unit_limit': 350, 'reason': 'Approved negotiated annual scope',
        }, format='json')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        issued = self.client.post(url, {
            'organization': self.organization.pk, 'amount_minor': 7_500_000,
            'unit_limit': 350, 'reason': 'Approved negotiated monthly scope',
        }, format='json')
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)
        self.assertEqual(issued.data['amount_minor'], 7_500_000)
        self.assertEqual(issued.data['plan_name'], 'Enterprise')
        subscription = OrganizationSubscription.objects.get(organization=self.organization)
        self.assertEqual(subscription.plan.code, 'free')
        self.assertEqual(subscription.effective_unit_limit, 5)

        self.client.force_authenticate(self.owner)
        reported = self.client.post(
            reverse('subscriptions:report-payment', args=(issued.data['id'],)),
            {'reference': 'ENT-VERIFIED-100'}, format='json',
        )
        self.assertEqual(reported.status_code, status.HTTP_202_ACCEPTED)
        self.client.force_authenticate(self.admin)
        confirmed = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(reported.data['id'], 'confirm')),
            {'reason': 'Matched to the verified bank deposit'}, format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan.code, 'enterprise')
        self.assertEqual(subscription.effective_unit_limit, 350)

    def test_reversed_payment_is_removed_from_net_collected_revenue(self):
        SubscriptionPlan.objects.filter(code='starter').update(setup_fee_minor=15_000)
        self.client.force_authenticate(self.owner)
        issued = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        reported = self.client.post(
            reverse('subscriptions:report-payment', args=(issued.data['id'],)),
            {'reference': 'REVERSAL-REF-01'}, format='json',
        )
        self.client.force_authenticate(self.admin)
        confirmed = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(reported.data['id'], 'confirm')),
            {'reason': 'Verified on payment provider statement'}, format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        payment = SubscriptionPayment.objects.get()
        reversal = self.client.post(
            reverse('subscriptions:admin-payment-reversal', args=(payment.pk,)),
            {'reason': 'Provider confirmed reversal of settlement'}, format='json',
        )
        self.assertEqual(reversal.status_code, status.HTTP_200_OK)
        summary = self.client.get(reverse('subscriptions:admin-revenue')).data
        self.assertEqual(summary['collected_minor'], 114_900)
        self.assertEqual(summary['reversed_minor'], 114_900)
        self.assertEqual(summary['net_collected_minor'], 0)
        self.assertEqual(summary['setup_fees_collected_minor'], 0)
        self.assertEqual(summary['setup_fees_reversed_minor'], 15_000)
        self.assertEqual(summary['monthly_fees_reversed_minor'], 99_900)

    def test_reversing_setup_fee_reopens_invoice_without_reissuing_fee(self):
        SubscriptionPlan.objects.filter(code='starter').update(setup_fee_minor=15_000)
        self.client.force_authenticate(self.owner)
        issued = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)
        invoice = SubscriptionInvoice.objects.get(pk=issued.data['id'])
        original_snapshot = (invoice.amount_minor, invoice.monthly_fee_minor, invoice.setup_fee_minor)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.setup_fee_invoiced)
        self.assertFalse(self.subscription.setup_fee_paid)

        report = self.client.post(
            reverse('subscriptions:report-payment', args=(invoice.pk,)),
            {'reference': 'REVERSIBLE-SETUP-FEE'}, format='json',
        )
        self.client.force_authenticate(self.admin)
        confirmed = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(report.data['id'], 'confirm')),
            {'reason': 'Matched independently to the provider statement'}, format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        payment = SubscriptionPayment.objects.get(invoice=invoice)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.setup_fee_paid)

        reversal_url = reverse('subscriptions:admin-payment-reversal', args=(payment.pk,))
        reversal = self.client.post(
            reversal_url, {'reason': 'Provider evidence confirmed the reversal'}, format='json',
        )
        self.assertEqual(reversal.status_code, status.HTTP_200_OK)
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.setup_fee_paid)
        self.assertTrue(self.subscription.setup_fee_invoiced)
        self.assertEqual(self.subscription.status, OrganizationSubscription.Status.PAST_DUE)

        self.client.force_authenticate(self.owner)
        subscription_response = self.client.get(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk},
        )
        invoice_view = next(row for row in subscription_response.data['invoices'] if row['id'] == str(invoice.pk))
        self.assertEqual(invoice_view['amount_minor'], sum(original_snapshot[1:]))
        self.assertEqual(invoice_view['amount_paid_minor'], 0)
        self.assertEqual(invoice_view['outstanding_minor'], original_snapshot[0])
        self.assertEqual(invoice_view['settlement_status'], SubscriptionPayment.Status.REVERSED)

        self.client.force_authenticate(self.admin)
        duplicate = self.client.post(
            reversal_url, {'reason': 'Duplicate reversal request'}, format='json',
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual((invoice.amount_minor, invoice.monthly_fee_minor, invoice.setup_fee_minor), original_snapshot)
        self.assertEqual(payment.status, SubscriptionPayment.Status.REVERSED)
        self.assertTrue(AuditLog.objects.filter(
            action='subscription.payment_reversed', object_id=str(payment.pk),
            metadata__amount_minor=payment.amount_minor,
        ).exists())

        OrganizationSubscription.objects.filter(pk=self.subscription.pk).update(
            current_period_end=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_authenticate(self.owner)
        renewal = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(renewal.status_code, status.HTTP_201_CREATED)
        self.assertEqual(renewal.data['setup_fee_minor'], 0)
        self.assertEqual(renewal.data['amount_minor'], 99_900)
        invoice.refresh_from_db()
        self.assertEqual((invoice.amount_minor, invoice.monthly_fee_minor, invoice.setup_fee_minor), original_snapshot)

    def test_grandfathered_setup_obligation_survives_unrelated_reversal_and_rental_invoice_is_untouched(self):
        SubscriptionPlan.objects.filter(code='starter').update(setup_fee_minor=20_000)
        self.subscription.setup_fee_invoiced = True
        self.subscription.save(update_fields=('setup_fee_invoiced',))
        tenant_user = get_user_model().objects.create_user(username='subscription-rent-tenant', password='test-password')
        tenant = Tenant.objects.create(
            organization=self.organization, user=tenant_user, first_name='Rental', last_name='Tenant',
            phone_number='+254700000099',
        )
        rent_invoice = RentInvoice.objects.create(
            organization=self.organization, tenant=tenant,
            period_start=timezone.localdate(), period_end=timezone.localdate(),
            due_date=timezone.localdate(), status=DocumentStatus.POSTED,
            total_cents=8_000, balance_cents=8_000,
        )

        self.client.force_authenticate(self.owner)
        issued = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(issued.data['setup_fee_minor'], 0)
        report = self.client.post(
            reverse('subscriptions:report-payment', args=(issued.data['id'],)),
            {'reference': 'GRANDFATHERED-MONTHLY-ONLY'}, format='json',
        )
        self.client.force_authenticate(self.admin)
        confirmed = self.client.post(
            reverse('subscriptions:admin-payment-review', args=(report.data['id'], 'confirm')),
            {'reason': 'Verified monthly subscription payment'}, format='json',
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        payment = SubscriptionPayment.objects.get()
        reversed_response = self.client.post(
            reverse('subscriptions:admin-payment-reversal', args=(payment.pk,)),
            {'reason': 'Verified reversal of unrelated monthly payment'}, format='json',
        )
        self.assertEqual(reversed_response.status_code, status.HTTP_200_OK)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.setup_fee_invoiced)
        self.assertFalse(self.subscription.setup_fee_paid)
        rent_invoice.refresh_from_db()
        self.assertEqual((rent_invoice.total_cents, rent_invoice.balance_cents), (8_000, 8_000))

        self.subscription.current_period_end = timezone.localdate() - timedelta(days=1)
        self.subscription.save(update_fields=('current_period_end',))
        self.client.force_authenticate(self.owner)
        renewal = self.client.post(
            reverse('subscriptions:organization-subscription'),
            {'organization': self.organization.pk, 'plan': 'starter'}, format='json',
        )
        self.assertEqual(renewal.status_code, status.HTTP_201_CREATED)
        self.assertEqual(renewal.data['setup_fee_minor'], 0)

    def test_login_response_exposes_only_own_staff_authorization_flag(self):
        response = self.client.post('/api/v1/accounts/login/', {
            'username': self.admin.username, 'password': 'test-password',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_staff'])
        ordinary = self.client.post('/api/v1/accounts/login/', {
            'username': self.owner.username, 'password': 'test-password',
        }, format='json')
        self.assertFalse(ordinary.data['is_staff'])
