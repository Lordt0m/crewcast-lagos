from datetime import datetime, timedelta
from typing import Optional
from django.utils import timezone

FRESH_THRESHOLD_HOURS = 4.0
EXPIRED_THRESHOLD_HOURS = 12.0


def get_freshness_state(last_successful_sync_at: Optional[datetime], now: Optional[datetime] = None) -> tuple[str, float]:
    """
    Computes data freshness category according to CrewCast policy:
    - 0 to 4 hours: 'fresh'
    - Over 4 to 12 hours: 'stale'
    - Over 12 hours or no sync: 'expired'
    Returns (state, age_seconds).
    """
    if last_successful_sync_at is None:
        return 'expired', float('inf')

    if now is None:
        now = timezone.now()

    age_seconds = max(0.0, (now - last_successful_sync_at).total_seconds())
    age_hours = age_seconds / 3600.0

    if age_hours <= FRESH_THRESHOLD_HOURS:
        return 'fresh', age_seconds
    elif age_hours <= EXPIRED_THRESHOLD_HOURS:
        return 'stale', age_seconds
    else:
        return 'expired', age_seconds


def get_effective_planning_display(recommendation_status: Optional[str], freshness_state: str) -> dict:
    """
    Enforces freshness constraints on recommendation presentation:
    - Fresh: shows current recommendation and source age.
    - Stale: presents last recommendation as historical context, prominently labels age,
             and strictly does NOT present a new 'suitable' status.
    - Expired / None: shows 'no current recommendation' with explanation.
    """
    if freshness_state == 'expired' or not recommendation_status or recommendation_status == 'unavailable':
        return {
            'actionable_status': None,
            'display_status': 'No current recommendation',
            'badge_class': 'status-expired',
            'banner_message': 'Forecast is too old to guide this job. Review scheduled retry.',
            'is_stale': False,
            'is_expired': True,
        }

    if freshness_state == 'stale':
        # "Do not present a new suitable status"
        is_suitable = (recommendation_status == 'suitable')
        return {
            'actionable_status': None if is_suitable else recommendation_status,
            'display_status': 'Historical context (Stale)' if is_suitable else f'{recommendation_status.capitalize()} (Historical)',
            'badge_class': 'status-stale',
            'banner_message': 'Forecast is stale. Review current conditions before using earlier recommendation.',
            'is_stale': True,
            'is_expired': False,
            'suppressed_suitable': is_suitable,
        }

    # Fresh
    return {
        'actionable_status': recommendation_status,
        'display_status': recommendation_status.capitalize(),
        'badge_class': f'status-{recommendation_status}',
        'banner_message': None,
        'is_stale': False,
        'is_expired': False,
    }
