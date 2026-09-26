# Architecture and decisions

## System shape

Use Django with server-rendered pages and modest progressive enhancement, PostgreSQL for durable records, and Redis for the task broker and disposable read cache. Celery Beat enqueues due-site checks; Celery workers perform outbound calls and evaluation. This stack makes the background and resilience behavior visible without making a separate frontend application the main project.

```text
Manager/browser → Django views → PostgreSQL (jobs, attempts, snapshots, recommendations)
                         ↘ Redis read cache
Celery Beat → due-site planner → Celery worker → Open-Meteo
                                       ↘ PostgreSQL budget reservation and sync lease
                                       ↘ normalization → snapshot → evaluation
```

The page request path reads stored results. It never waits for the provider. The worker uses a narrow `ForecastProvider.fetch(site, now)` interface, with a real Open-Meteo adapter and fixture adapter for deterministic tests and read-only demo replay. `evaluate(job, snapshot)` is pure and returns status plus reasons. Persistence owns uniqueness, transitions, and transaction scope. Avoid wrappers that only forward method calls.

## Durable records

| Record | Key fields and invariants |
| --- | --- |
| Site | Name, requested coordinates, active flag; one forecast stream per site. |
| Job | Site, title, local window stored as UTC instants, revision, policy version; immutable past recommendations survive edits. |
| WeatherPolicyVersion | Eight caution/stop values, units, creation time; changes create a version, not an in-place rewrite. |
| SyncAttempt | Site, planned time, actual start/end, attempt number, outcome, HTTP category or validation error, next retry, snapshot link if successful. One row per actual attempt or explicit deferral. |
| ForecastSnapshot | Site, normalized content hash, returned grid coordinates, first retrieval time, hour coverage, immutable hourly values. Unique `(site, content_hash)`; a repeat fetch links to the same snapshot. |
| Recommendation | Job revision, policy version, snapshot, evaluation time, status, metric reasons and window coverage. Unique per input version. |
| BudgetWindow | Lagos local date, reserved outbound-call count; atomic increment under row lock before each HTTP attempt. |

Track the last successful retrieval from `SyncAttempt`; do not overwrite a snapshot's first retrieval time. Use a transaction-level uniqueness or row lock for the due-site claim and idempotent snapshot commit. A worker crash after reserving a call may count a call that never went out; conservative overcount is preferable to untracked outbound traffic. Expose both attempted calls and deferrals so the budget is auditable.

The provider response is validated before commit: array lengths and units match, timestamps are ordered and timezone-aware after normalization, coordinates are plausible, required values are numeric or explicitly missing, and coverage includes the planned window. Record the requested coordinates and returned grid cell separately. Do not infer a provider issue time from `generationtime_ms`.

## Cache and recovery

Cache the assembled current job-list response by job revision, policy version, and snapshot/retrieval marker, with a short TTL of at most 30 minutes. Recompute data age at render time, so a cache hit cannot make a four-hour-old retrieval look new. Invalidate on job or policy change and successful sync. If Redis is unavailable for cache reads, Django reads PostgreSQL and records a degraded cache signal. If Redis is unavailable as the Celery broker, Beat/worker processing pauses and Operations reports that no recent worker heartbeat exists; the pages still load stored data and the freshness clock advances.

Retry only errors likely to recover. Cap exponential backoff but never shorten a server `Retry-After` on `429`; never bypass the budget or circuit with a public refresh button. Record failure category and next attempt in the database before another task is queued. A manual manager retry may be added only if it uses the same budget and idempotency path; it is not required for the MVP.

## Verification and operations

Use a real PostgreSQL service in CI for uniqueness and concurrency tests, Redis for worker integration tests, and an injected clock and random source for predictable backoff. Keep the pure evaluator test suite fast. Integration tests should verify a full success, duplicate fetch, concurrent sync, timeout/retry/expiry/recovery, and Redis cache loss. Test a real browser at 320px and 200% zoom once the UI exists.

Operations shows: last scheduler tick, last worker heartbeat, each site's last successful retrieval and next due time, today’s used/reserved budget, recent attempt outcomes, circuit state, and cache degradation. The public demo may expose a filtered, synthetic version without hostnames, stack traces, credentials, or raw provider errors.

## Decisions recorded

- [0001 — Store immutable forecast versions separately from fetch attempts](docs/adr/0001-separate-forecast-versions-from-fetch-attempts.md).
- [0002 — Keep provider access in scheduled workers](docs/adr/0002-keep-provider-access-in-scheduled-workers.md).

These choices preserve explainability under retries and prevent site visitors or ordinary page loads from consuming the upstream budget. Exact dependency versions and hosting are implementation decisions for the future repository; recheck current support and account terms before deployment.
