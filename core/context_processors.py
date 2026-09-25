from django.conf import settings
from django.utils import timezone

def app_context(request):
    """Provides common context variables across all templates."""
    return {
        'DEMO_MODE': getattr(settings, 'DEMO_MODE', False),
        'lagos_now': timezone.now(),
        'app_name': 'CrewCast Lagos',
    }
