from django.http import HttpResponse
from django.conf import settings


class LocalCorsMiddleware:
    """Small safety-net CORS middleware for local Next.js development.

    django-cors-headers should handle this, but this middleware guarantees
    headers are present even for early errors or OPTIONS preflight requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin')
        allowed = set(getattr(settings, 'CORS_ALLOWED_ORIGINS', []))
        allow_all = getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False)

        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if origin and (allow_all or origin in allowed):
            response['Access-Control-Allow-Origin'] = origin
            response['Vary'] = 'Origin'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
            response['Access-Control-Max-Age'] = '86400'
        return response
