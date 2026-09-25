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
    Honors Retry-After header if provided.
    Caps at max_delay_seconds.
    """
    factor = 2 ** max(0, attempt_number - 1)
    delay = (base_seconds * factor) + jitter_seconds

    if retry_after is not None:
        delay = max(delay, float(retry_after))

    return min(delay, max_delay_seconds)
