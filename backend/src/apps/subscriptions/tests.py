from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Invoice as RentInvoice
from apps.organizations.models import Organization, OrganizationMembership
from apps.properties.models import Building, Property, Unit
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

    def test_payment_report_never_activates_plan_until_staff_verification(self):
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
        plan.price_minor += 1
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
        self.assertEqual(summary['collected_minor'], 99_900)
        self.assertEqual(summary['reversed_minor'], 99_900)
        self.assertEqual(summary['net_collected_minor'], 0)

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

