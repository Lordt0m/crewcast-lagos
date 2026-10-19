# CrewCast Lagos

> Weather-aware job planning aid for outdoor service dispatchers in Lagos, Nigeria. Example jobs are synthetic; displayed forecasts require a real provider retrieval.

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Django 5.2](https://img.shields.io/badge/django-5.2-green.svg)](https://www.djangoproject.com/)

CrewCast answers the central operational question for outdoor service operations: **which scheduled jobs need attention because the latest forecast has changed, and can dispatchers trust the age of that forecast?**

---

## Key Invariants & Architectural Principles

1. **Zero Provider Requests on Page Loads**  
   Every web page view (`/`, `/jobs/<id>/`, `/operations/`) queries only stored PostgreSQL records and optional Redis cache. Live forecast synchronization runs outside web requests, via Celery locally or the scheduled GitHub Actions job for a hosted demo. Retired `/demo/replay/` bookmarks permanently redirect to the planning board.

2. **Atomic Lagos Calendar Daily Budget Cap (300 calls/day)**  
   Open-Meteo free non-commercial API usage is guarded by an atomic row-locked daily budget tracker (`BudgetWindow`). Even with overlapping sync processes, outbound requests are capped at 300 per `Africa/Lagos` calendar day. Once exhausted, background sync attempts are recorded as `deferred` without failing local views.

3. **Immutable Content Hash Snapshots & Provenance**  
   Forecast data is normalized and deduplicated by SHA-256 content hash in `ForecastSnapshot`. If identical weather data is returned across multiple polling cycles, only one snapshot is stored while each attempt is logged in `SyncAttempt` with timestamps, durations, and HTTP statuses. The current forecast follows the latest verified successful attempt, including when content changes A→B→A.

4. **Pure Recommendation Evaluator**  
   Recommendation evaluation (`core/evaluator.py`) is a pure function. It accepts UTC job windows, policy thresholds, and hourly forecast arrays; computes intersecting hourly intervals; aggregates maximum metrics; and returns structured crossed threshold reasons with no database or network side-effects.

5. **3-Tier Freshness Policy & Suitable Suppression**  
   - **Fresh ($\le$ 4 hours):** Recommendation status active, source retrieval age displayed.
   - **Stale (4 to 12 hours):** Prior recommendation shown as historical context; **suitable status is strictly suppressed** to prevent unsafe assumptions on aging data.
   - **Expired (> 12 hours):** Recommendation status suppressed to "No current recommendation".

6. **Provider Circuit Breaker**  
   A provider-wide circuit breaker (`ProviderCircuitState`) trips from `CLOSED` to `OPEN` after 3 consecutive transient failures (`5xx`, timeouts). During the 15-minute cool-off period, outbound syncs are deferred. Afterwards, it tests exactly 1 `HALF_OPEN` probe before returning to `CLOSED`.

7. **Advancing Age Cache Architecture**  
   Job board query payloads are cached in Redis (`X-CrewCast-Cache: HIT`/`MISS`), but displayed forecast age and freshness tiers are computed at request render time from stored UTC timestamps. Cache hits advance in age naturally. If Redis becomes unavailable, the system gracefully falls back to PostgreSQL without 500 errors.

8. **Server-Side Demo Mode (`DEMO_MODE=True`)**  
   When demo mode is active, state-changing HTTP methods are blocked across the site with HTTP 403 Forbidden, including sign-in and admin routes. Background workers can still retrieve real forecasts.

---


## Data Attribution & Non-Commercial Compliance

Weather forecasts are provided by [Open-Meteo](https://open-meteo.com) under Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Scope:** Non-commercial educational and operational prototype.
- **Payload Minimization:** Requests are strictly constrained to 4 hourly metrics: `precipitation_probability`, `precipitation`, `wind_gusts_10m`, and `apparent_temperature`.
- **Traffic Ceiling:** Maximum 300 calls/day; normal 10-site schedule consumes ~80 calls/day.

---

## Local Setup & Quickstart

### Prerequisites
- Python 3.13+
- PostgreSQL 16+ (or local SQLite fallback)
- Redis 7+ (or local memory cache fallback)

### 1. Virtual Environment
```bash
# From the CrewCast Lagos project directory:

python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment Configuration
Copy the example environment file:
```bash
cp .env.example .env
```

### 3. Database Migrations
```bash
python manage.py migrate
```

### 4. Seed Synthetic Lagos Data
Populate 6 example Lagos sites, default policy thresholds, and jobs:
```bash
python manage.py seed_demo_data
```
The command does not create an account, forecast, successful sync attempt, or usage count. Forecasts remain pending until the worker retrieves data from Open-Meteo. Older snapshots, attempts, and budget windows from previous versions are conservatively treated as unverified after migration. Legacy budget counters remain in place to enforce the daily cap.

If an older seed already created the `dispatcher` account, its published demo password is rejected even when `DEMO_MODE=False`. Reset that password to a private one or disable the account before using manager features. This update does not silently delete existing accounts or data.

### 5. Run the Application
Start the Django development server:
```bash
python manage.py runserver 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser:
- **Job Board:** [http://localhost:8000/](http://localhost:8000/)
- **Operations Dashboard:** [http://localhost:8000/operations/](http://localhost:8000/operations/)
- **Health Check Endpoint:** [http://localhost:8000/health/](http://localhost:8000/health/)

### 6. Background Workers (Required for live sync)
In separate terminal windows:
```bash
# Celery Worker
celery -A crewcast worker -l info

# Celery Beat Scheduler
celery -A crewcast beat -l info
```

The development server alone does not fetch live forecasts. The provided Docker Compose file is local-development only: its services bind to loopback and use development credentials. Do not expose it publicly. The image's default web command uses Gunicorn and `DEBUG=False`, and startup requires a unique `SECRET_KEY`, explicit `ALLOWED_HOSTS`, and PostgreSQL `DATABASE_URL`. Before a public deployment, also set `DEMO_MODE=True`, configure HTTPS at the edge, run `collectstatic`, and choose either the Celery processes or the GitHub Actions schedule below. Review or disable any old `dispatcher` login before ever enabling manager writes.

## Scheduled forecast refresh with GitHub Actions

The workflow in `.github/workflows/forecast-sync.yml` checks due sites hourly at minute 17 UTC. It invokes `python manage.py sync_due_forecasts` once, then exits; it is not an always-on worker. GitHub schedules can be delayed or occasionally dropped, so the website continues to show forecast age and suppresses stale recommendations. The workflow is disabled until a shared hosted PostgreSQL database exists.

To activate it for a hosted demo:

1. Provision a PostgreSQL database reachable over TLS from both the website and GitHub-hosted runners. For Neon Free, use the pooled connection URL for normal web and scheduled-job traffic, and the direct (non-`-pooler`) URL for migrations and seed commands. Do not use the local SQLite file or the Docker Compose database; neither is accessible to GitHub Actions. Include `sslmode=require` (or stronger provider-recommended TLS options) in the connection URLs.
2. Deploy the Django web process with the same pooled `DATABASE_URL` as the scheduled job, a unique `SECRET_KEY`, `DEBUG=False`, explicit `ALLOWED_HOSTS`, `DEMO_MODE=True`, and `FORECAST_RUNNER=github_actions`. Run `python manage.py migrate` and `python manage.py seed_demo_data` using the direct URL, and `python manage.py collectstatic --noinput` during deployment. Do not run Celery Beat at the same time as the GitHub schedule.
3. In the repository's **Settings → Secrets and variables → Actions**, add secrets `DATABASE_URL` and `CREWCAST_SECRET_KEY`. Use the hosted database URL and a unique secret value; never commit either one. Add repository variable `CREWCAST_FORECAST_ENABLED` with value `true` only after the database has been migrated and seeded.
4. Run **Forecast refresh → Run workflow** once, then check the run result and `/operations/`. The database-backed scheduled-check card records the last invocation even when no site was due. The web pages and the workflow must point to the same database.

The workflow does not host Django or PostgreSQL. Without a deployed web app and shared database, publishing the repository alone will not produce a public live-data website. If the cache is not hosted, reads fall back to PostgreSQL; Redis is not required for this scheduled path. GitHub may disable scheduled workflows in a public repository after 60 days without repository activity; re-enable the workflow if that happens.

---

## Running Automated Tests

Run the full suite with pytest:
```bash
pytest -v
```

The test suite covers:
- Stack health & component reporting (`tests/test_stack_health.py`)
- Site, job, and policy domain models (`tests/test_domain_models.py`)
- Provider adapters, normalization, and hashing (`tests/test_provider_adapter.py`)
- Atomic budget reservation and snapshot deduplication (`tests/test_budget_and_snapshots.py`)
- Pure recommendation evaluator table-driven tests (`tests/test_pure_evaluator.py`)
- Retry policy, circuit breaker, and freshness suppression (`tests/test_retry_circuit_freshness.py`)
- Responsive job board and detail views (`tests/test_board_and_detail_views.py`)
- Operations telemetry and advancing age cache (`tests/test_operations_and_cache.py`)
- Read-only demo mode and retired replay redirects (`tests/test_demo_and_replay.py`)
- Production configuration fail-closed checks (`tests/test_deployment_config.py`)

CI requires PostgreSQL and Redis; it fails instead of silently substituting SQLite or an in-memory cache. Local tests may use SQLite and an in-memory cache when those services are unavailable.

---

## Interface development

The redesigned interface remains server-rendered Django. `static/css/field.css` owns the weather field-bulletin design: self-hosted Barlow typography, signal yellow, ink and cobalt. The font licence is included under `static/fonts/`. `DESIGN.md` records the implemented system.

Optional presentation enhancement is authored in `frontend/crewcast.ts`; generated `static/js/crewcast.js` is committed so Python-only hosting still works. To change it, run `npm ci`, `npm run build`, then `npm test`. Run `python manage.py collectstatic --noinput` before Django tests, as required by the manifest static storage. CI checks the TypeScript build, cancellation tests and generated-file drift alongside the existing backend suite.

The first public introduction has a one-shot entrance. Replay sequences highlight existing, fully visible explanations. Repeated activation settles them immediately; keyboard and reduced-motion activation show the complete explanation. No enhancement fetches weather, evaluates policies or changes permissions.

Date links retain a native `#planning` destination. With enhancement, only the Django-rendered board fragment is requested; its strip position and horizontal offset stay fixed, browser Back works, and keyboard focus follows the selected date. Requests are cancelled and generation-checked so an obsolete response cannot replace a newer selection. Failed loads retain current jobs and offer retry or full-page navigation. Responses vary on `X-CrewCast-Board`; no browser data cache or prefetch can conceal advancing forecast age. WOFF2 Latin font subsets reduce the two font downloads to about 48 KB combined; original licensed sources remain available. Introductory motion skips devices reporting at most two cores, data-saving mode or 2G/3G connections.

## Design System & Accessibility

The user interface adheres to the design engineering principles in `.agents/skills/` (`better-interface`, `better-typography`, `better-colors`, `better-ui`, `emil-design-eng`):
- **Typography:** Self-hosted Barlow Condensed display and Barlow reading text, with tabular numerals for dates and measurements.
- **Color Independence:** Status badges combine high-contrast semantic background tokens with SVG icons and explicit textual labels (e.g. `Suitable`, `Caution`, `Unsuitable`, `Historical`).
- **Responsive Layout:** The job board reflows to one column; the seven-day selector remains horizontally scrollable. Wide data tables use labelled, focusable horizontal scroll regions.
- **Keyboard Navigation:** Full focus state rings (`:focus-visible`) and semantic landmark structures (`<header>`, `<nav>`, `<main>`, `<footer>`, `<section>`).
