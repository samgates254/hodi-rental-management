from apps.notifications.models import Notification


def notify_user(*, user, type, title, body='', organization=None, payload=None):
    if user is None:
        return None
    return Notification.objects.create(
        user=user,
        organization=organization,
        type=type,
        title=title,
        body=body,
        payload=payload or {},
    )
