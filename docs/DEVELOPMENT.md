# Development Commands

Run checks:

```bash
env/bin/python manage.py check
```

Run the installed-app tests:

```bash
env/bin/python manage.py test apps.accounts
```

As domain tests are added, include their app labels, for example:

```bash
env/bin/python manage.py test apps.accounts apps.organizations apps.properties apps.tenants apps.leases
```
