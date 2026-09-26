from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse


class DemoReadOnlyMiddleware:
    """Reject writes at the HTTP boundary, including auth and admin routes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEMO_MODE and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            message = 'State-changing actions are disabled in Demo Mode.'
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                return JsonResponse({'error': message}, status=403)
            return HttpResponseForbidden(message)
        return self.get_response(request)
