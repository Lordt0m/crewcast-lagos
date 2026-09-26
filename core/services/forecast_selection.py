from core.models import Site, SyncAttempt


def latest_verified_success(site: Site) -> SyncAttempt | None:
    """Return the latest actual retrieval, not the newest unique content row."""
    return (
        SyncAttempt.objects.select_related('snapshot')
        .filter(
            site=site,
            source_kind='worker',
            outcome='success',
            snapshot__source_kind='provider',
        )
        .order_by('-completed_at', '-pk')
        .first()
    )
