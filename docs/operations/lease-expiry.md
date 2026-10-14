# Scheduled lease expiry

HODI exposes the existing lease lifecycle operation as the Django command
`expire_due_leases`. Run it every 15 minutes from one deployment scheduler or
host cron. The task uses the Africa/Nairobi business date and only selects
active leases whose inclusive `end_date` is before that date. A lease remains
active for its complete final calendar day.

Example system cron entry (adjust the checkout and virtualenv paths for the
deployment):

```cron
*/15 * * * * cd /srv/hodi/backend && /srv/hodi/backend/.venv/bin/python manage.py expire_due_leases >> /var/log/hodi/lease-expiry.log 2>&1
```

Each lease is finalized through the existing locked, transactional
`expire_lease` service. A scheduled termination becomes terminated after its
final day and receives its existing end notification once. Ordinary expiry
does not create a tenant notification. The audit entry identifies
`source=scheduled_expiry`; automated runs have no human actor. If one lease
fails, its transaction rolls back, the command reports its lease ID and exits
with an error, and later runs can retry it. Other leases in the same run can
still complete.

The scheduler must capture standard output and error and alert on non-zero
exit status. On a failed lease, standard error reports only its lease ID and
exception class; it intentionally omits exception text, which could contain
personal or financial details. Review the captured command output, then allow
the next scheduled run to retry the lease. Keep one scheduled job per
environment. Database row locks serialize concurrent expiry attempts, but
PostgreSQL multi-worker behavior must be verified in an isolated PostgreSQL
environment before relying on multiple simultaneous schedulers.

Run the command manually from `backend/` to verify scheduler wiring in a
non-production environment. It does not contact external services. Do not
run it against production until the configured database, audit retention,
notification delivery, and scheduler monitoring have been reviewed.
