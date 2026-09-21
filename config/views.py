from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Return service and database readiness without exposing internals."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return JsonResponse({'status': 'unhealthy'}, status=503)

    return JsonResponse({'status': 'ok'})