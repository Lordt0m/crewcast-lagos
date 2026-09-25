# Separate forecast versions from fetch attempts

Status: accepted for the CrewCast plan.

A repeated provider response is a new retrieval event but not a new forecast content version. Store every attempted fetch, including failures and identical successes, as a `SyncAttempt`; keep normalized `ForecastSnapshot` versions immutable and deduplicated by site and content hash. Derive freshness from the latest successful attempt, while recommendations reference the immutable snapshot and policy version that produced them. This adds a second record type but avoids false history entries and keeps both recovery and provenance auditable. The alternative of overwriting one current forecast would lose the reasons behind earlier job recommendations.
