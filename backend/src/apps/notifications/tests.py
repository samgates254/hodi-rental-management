from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.organizations.models import Organization


class NotificationApiTests(APITestCase):
    def test_users_only_read_their_own_notifications(self):
        user_model = get_user_model()
        owner = user_model.objects.create_user(username='owner', password='password')
        other = user_model.objects.create_user(username='other', password='password')
        organization = Organization.objects.create(name='Rongai Homes')
        note = Notification.objects.create(
            user=owner,
            organization=organization,
            type='INVOICE_POSTED',
            title='Invoice posted',
            body='Due now',
        )
        Notification.objects.create(
            user=other,
            organization=organization,
            type='INVOICE_POSTED',
            title='Other invoice',
        )
        self.client.force_authenticate(owner)
        listing = self.client.get('/api/v1/notifications/')
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in listing.data], [note.pk])
        hidden = self.client.get(f'/api/v1/notifications/{note.pk + 1}/')
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)
        marked = self.client.post(f'/api/v1/notifications/{note.pk}/read/')
        self.assertEqual(marked.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(marked.data['read_at'])
        second = Notification.objects.create(user=owner, type='PAYMENT_RECEIVED', title='Paid')
        cleared = self.client.post('/api/v1/notifications/read-all/')
        self.assertEqual(cleared.status_code, status.HTTP_200_OK)
        self.assertEqual(cleared.data['updated'], 1)
        second.refresh_from_db()
        self.assertIsNotNone(second.read_at)
