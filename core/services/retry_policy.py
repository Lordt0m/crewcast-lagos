from typing import Optional

MAX_SYNC_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 600.0  # 10 minutes max backoff delay


def calculate_retry_delay(
    attempt_number: int,
    retry_after: Optional[int] = None,
    base_seconds: float = BASE_BACKOFF_SECONDS,
    max_delay_seconds: float = MAX_BACKOFF_SECONDS,
    jitter_seconds: float = 0.0,
) -> float:
    """
    Computes bounded exponential backoff delay:
    - attempt 1 -> base * 1 + jitter
    - attempt 2 -> base * 2 + jitter
    - attempt 3 -> base * 4 + jitter
    Caps exponential backoff at max_delay_seconds, but never shortens a
    provider-supplied Retry-After delay.
    """
    factor = 2 ** max(0, attempt_number - 1)
    delay = min((base_seconds * factor) + jitter_seconds, max_delay_seconds)

    if retry_after is not None:
        delay = max(delay, float(retry_after))

    return delay
