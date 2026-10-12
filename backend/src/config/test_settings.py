import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


BACKEND_DIR = Path(__file__).resolve().parents[2]
SETTINGS_CHECK = "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"


class DatabaseConfigurationTests(SimpleTestCase):
    def settings_environment(self, *, production):
        environment = os.environ.copy()
        prefixes = ('DJANGO_', 'DB_', 'MPESA_', 'EMAIL_', 'CORS_', 'CSRF_')
        for name in tuple(environment):
            if name.startswith(prefixes) or name == 'DATABASE_URL':
                environment.pop(name, None)
        environment.update({
            'PYTHON_DOTENV_DISABLED': '1',
            'DJANGO_SETTINGS_MODULE': 'config.settings',
            'PYTHONPATH': os.pathsep.join(filter(None, (
                str(BACKEND_DIR / 'src'),
                environment.get('PYTHONPATH', ''),
            ))),
            'DJANGO_ENV': 'production' if production else 'development',
        })
        if production:
            callback_token = 'configuration-test-token-1234567890'
            environment.update({
                'DJANGO_DEBUG': 'False',
                'DJANGO_SECRET_KEY': 'test-only-secret-key-' + ('x' * 60),
                'DJANGO_ALLOWED_HOSTS': 'api.example.invalid',
                'DJANGO_EMAIL_HOST': 'smtp.example.invalid',
                'DJANGO_DEFAULT_FROM_EMAIL': 'hodi@example.invalid',
                'DJANGO_CACHE_BACKEND': 'django.core.cache.backends.db.DatabaseCache',
                'DJANGO_CACHE_LOCATION': 'hodi_cache',
                'CORS_ALLOWED_ORIGINS': 'https://app.example.invalid',
                'MPESA_ENVIRONMENT': 'sandbox',
                'MPESA_CALLBACK_AUTH_TOKEN': callback_token,
                'MPESA_CALLBACK_URL': (
                    'https://api.example.invalid/api/v1/billing/mpesa/callback/'
                    f'{callback_token}/'
                ),
            })
        return environment

    def run_settings(self, environment):
        return subprocess.run(
            [sys.executable, '-c', SETTINGS_CHECK],
            cwd=BACKEND_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_production_rejects_sqlite_fallback_when_database_url_is_absent(self):
        result = self.run_settings(self.settings_environment(production=True))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Production database backend must be PostgreSQL.', result.stderr)

    def test_production_rejects_sqlite_database_url(self):
        environment = self.settings_environment(production=True)
        environment['DATABASE_URL'] = 'sqlite:///:memory:'

        result = self.run_settings(environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Production database backend must be PostgreSQL.', result.stderr)

    def test_valid_postgresql_database_url_passes_engine_validation_without_connecting(self):
        environment = self.settings_environment(production=True)
        environment['DATABASE_URL'] = 'postgres://test_user:unused@example.invalid:5432/test_db'

        result = self.run_settings(environment)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'django.db.backends.postgresql')

    def test_production_postgresql_db_engine_fallback_remains_supported(self):
        environment = self.settings_environment(production=True)
        environment.update({
            'DB_ENGINE': 'django.db.backends.postgresql',
            'DB_NAME': 'test_db',
            'DB_USER': 'test_user',
            'DB_PASSWORD': 'unused',
            'DB_HOST': 'example.invalid',
            'DB_PORT': '5432',
        })

        result = self.run_settings(environment)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'django.db.backends.postgresql')

    def test_local_sqlite_configuration_remains_supported(self):
        result = self.run_settings(self.settings_environment(production=False))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'django.db.backends.sqlite3')

    def test_existing_production_debug_validation_remains_intact(self):
        environment = self.settings_environment(production=True)
        environment['DJANGO_DEBUG'] = 'True'
        environment['DATABASE_URL'] = 'sqlite:///:memory:'

        result = self.run_settings(environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_DEBUG must be false in production.', result.stderr)
