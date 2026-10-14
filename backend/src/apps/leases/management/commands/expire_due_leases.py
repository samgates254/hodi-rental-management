from django.core.management.base import BaseCommand, CommandError

from application.services.leases import expire_due_leases


class Command(BaseCommand):
    help = 'Finalize active leases after their inclusive Nairobi end date.'

    def handle(self, *args, **options):
        processed, failures = expire_due_leases()
        self.stdout.write(f'Lease expiry run complete: processed={processed}, failed={len(failures)}.')
        for lease_id, error in failures:
            self.stderr.write(
                self.style.ERROR(
                    f'Lease {lease_id} expiry failed ({type(error).__name__}); '
                    'its transaction was rolled back and it may be retried.'
                )
            )
        if failures:
            raise CommandError(
                f'{len(failures)} lease expiry operation(s) failed; '
                'review the sanitized failure details above and retry on the next scheduled run.'
            )
