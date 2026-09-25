# Small, testable delivery tickets

Complete in order; each ticket should leave the app runnable and have one reviewable change set. Do not combine several tickets into a single opaque implementation pass. The test names below describe behavior, not required filenames.

## 01 — Repository and local stack

Create the Django project, PostgreSQL database, Redis, Celery worker and Beat processes, environment example, and a repeatable local startup command. A health view distinguishes web, database, broker, and worker heartbeat. **Check:** fresh clone starts locally; CI connects to real PostgreSQL and Redis; no secrets in tracked files.

## 02 — Site, job, and policy records

Implement one-team manager sign-in, at most 10 active sites, jobs, and versioned policy values. Store local input as aware UTC instants and display `Africa/Lagos`. **Check:** rejects invalid job windows, out-of-horizon jobs, invalid thresholds, and unauthorized edits; a policy edit does not rewrite a historical version.

## 03 — Provider adapter and normalization

Add a narrow Open-Meteo adapter and fixture adapter. Request only the four needed hourly variables. Normalize times, units, requested site and returned grid cell; validate arrays, coverage, missing values, and schema. **Check:** saved fixtures cover normal, partial, malformed, and changed responses; tests make zero live calls; provider processing time is not stored as an issue timestamp.

## 04 — Budget and due-site scheduling

Beat finds sites due every three hours; worker reserves a budget slot atomically before every outbound attempt. Claim one due sync per site so parallel workers cannot duplicate it. **Check:** concurrent test keeps attempts at or below the configured 300/day cap; same site is not fetched twice for one due slot; budget deferrals appear in Operations.

## 05 — Attempts and immutable snapshots

Record each real attempt and explicit deferral; deduplicate snapshots by normalized content hash under a database constraint. Link every successful attempt to its snapshot, even when identical. **Check:** two identical responses create two successful attempts, one snapshot, and a newer last-successful-retrieval time; concurrent commits leave one snapshot.

## 06 — Pure recommendation evaluator

Evaluate a job window using maxima over intersecting hourly intervals and both threshold bands; return every crossed reason. Distinguish incomplete coverage from a weather status. **Check:** table-driven tests for exact boundaries, partial hours, midnight, missing metrics, and policy-version changes; duplicate inputs create no duplicate recommendation.

## 07 — Retry, circuit, and freshness

Add timeout and `429`/`5xx` retries, `Retry-After`, bounded jitter, permanent malformed-data failure, simple provider circuit, and fresh/stale/expired policy. **Check:** controlled-clock tests prove attempt limit, budget inclusion, next retry, circuit probe, no current suitable status when stale, expiry, and recovery to fresh.

## 08 — Job board and detail

Build responsive server-rendered board and detail pages from stored results, including age, source, reasons, history comparison, and pending/missing states. **Check:** manager flow works by keyboard; 320px and 200% zoom show all controls and reasons; labels and status do not depend on color; a page load makes no provider call.

## 09 — Operations and Redis cache

Add worker and scheduler heartbeat, per-site sync timeline, daily budget, last error and next retry, circuit state, and cache health. Cache the board response without caching its displayed age. **Check:** a cache hit reports the true advancing age; Redis cache loss falls back to PostgreSQL; the broker loss is shown as degraded while stored pages still load.

## 10 — Read-only demo and failure replay

Seed only synthetic Lagos sites and jobs. Add a public read-only board backed by scheduled live forecasts, plus a separate fixture scenario selector showing success, timeout, stale data, and recovery without mutating shared data. Disable all state-changing web routes server-side in demo mode, including signed-in manager routes. **Check:** every public write and force-sync attempt fails; normal page views send no provider requests; the scheduled worker fetches live data within budget; replay is visibly labelled simulation and historical reasons match fixtures.

## 11 — Documentation, deployment, and final verification

Document setup, decisions, tests, data attribution, free API restriction, demo limitations, and architecture. If deployment is authorized and feasible, deploy the web, live forecast worker, Beat, PostgreSQL, and Redis together; recheck current provider and host terms before choosing a plan. **Check:** complete test suite and an end-to-end failure demonstration pass in the deployed environment; confirm public read-only behavior, a successful scheduled live sync, correct freshness display, bounded Open-Meteo traffic, fixture replay labelling, and attribution. Report exact commands/results and a working URL, or state the concrete hosting blocker without claiming deployment.

## Release gate

There is no fixed percentage coverage target. The gate is evidence: deterministic core rules, real database concurrency, worker retry behavior, stale/expiry transitions, browser accessibility and narrow layout checks, and a transparent deployment report. No ticket closes merely because the happy path rendered once.
