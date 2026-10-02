from apps.audit.models import AuditLog


def record_audit(
    *,
    action,
    object_type,
    object_id,
    actor=None,
    organization=None,
    metadata=None,
    request=None,
):
    ip_address = None
    if request is not None:
        ip_address = request.META.get('REMOTE_ADDR') or None
    return AuditLog.objects.create(
        actor=actor,
        organization=organization,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        metadata=metadata or {},
        ip_address=ip_address,
    )
