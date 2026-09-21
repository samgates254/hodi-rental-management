import uuid

from django.utils.deprecation import MiddlewareMixin


class RequestIDMiddleware(MiddlewareMixin):
    """Attach a correlation ID to every request and response."""

    def process_request(self, request):
        request.request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())

    def process_response(self, request, response):
        response['X-Request-ID'] = getattr(request, 'request_id', str(uuid.uuid4()))
        return response