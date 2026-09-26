# CrewCast Lagos

> Weather-aware job planning aid for outdoor service dispatchers in Lagos, Nigeria. Example jobs are synthetic; displayed forecasts require a real provider retrieval.

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Django 5.2](https://img.shields.io/badge/django-5.2-green.svg)](https://www.djangoproject.com/)

CrewCast answers the central operational question for outdoor service operations: **which scheduled jobs need attention because the latest forecast has changed, and can dispatchers trust the age of that forecast?**

---

## Key Invariants & Architectural Principles

1. **Zero Provider Requests on Page Loads**  
   Every web page view (`/`, `/jobs/<id>/`, `/operations/`, `/demo/replay/`) queries only local PostgreSQL records and Redis cache. Live forecast synchronization runs strictly in the background via Celery Beat and Celery Workers.

2. **Atomic Lagos Calendar Daily Budget Cap (300 calls/day)**  
   Open-Meteo free non-commercial API usage is guarded by an atomic row-locked daily budget tracker (`BudgetWindow`). Even with multiple parallel Celery workers, outbound requests are capped at 300 per `Africa/Lagos` calendar day. Once exhausted, background sync attempts are recorded as `deferred` without failing local views.

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

## Interactive Failure Replay Sandbox

Visit `/demo/replay/` for an interactive, in-memory resilience sandbox that demonstrates edge cases without mutating shared database state:

| Scenario | Invariant Demonstrated | Expected Signal |
| :--- | :--- | :--- |
| **1. Normal Success** | Clear weather work window | `Suitable` · All metrics below caution thresholds |
| **2. Caution Warning** | Rain prob 55% or gusts 28 km/h | `Caution` · Specific metric and interval reasons |
| **3. Severe Rainstorm** | Precipitation 7.5 mm/h or gusts 44 km/h | `Unsuitable` (Stop Work) |
| **4. Timeout & Retry** | HTTP 504 Gateway Timeout | `Transient Error` · Exponential backoff & retry delay |
| **5. Stale Data** | Forecast retrieved 7.5 hours ago | `Suitable Suppression` · Marked Historical Context |
| **6. Expired Data** | Forecast retrieved 14 hours ago | `No current recommendation` |
| **7. Circuit Breaker** | 3 consecutive upstream timeouts | `CLOSED` $\rightarrow$ `OPEN` $\rightarrow$ `HALF_OPEN` $\rightarrow$ `CLOSED` |

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
- **Failure Replay Sandbox:** [http://localhost:8000/demo/replay/](http://localhost:8000/demo/replay/)
- **Health Check Endpoint:** [http://localhost:8000/health/](http://localhost:8000/health/)

### 6. Background Workers (Required for live sync)
In separate terminal windows:
```bash
# Celery Worker
celery -A crewcast worker -l info

# Celery Beat Scheduler
celery -A crewcast beat -l info
```

The development server alone does not fetch live forecasts. The provided Docker Compose file is local-development only: its services bind to loopback and use development credentials. Do not expose it publicly. The image's default web command uses Gunicorn and `DEBUG=False`, and startup now requires a unique `SECRET_KEY`, explicit `ALLOWED_HOSTS`, and PostgreSQL `DATABASE_URL`. Before a public deployment, also set `DEMO_MODE=True`, configure HTTPS at the edge, run `collectstatic`, and run the worker and scheduler alongside the web app. Review or disable any old `dispatcher` login before ever enabling manager writes.

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
- Read-only demo mode and failure replay (`tests/test_demo_and_replay.py`)
- Production configuration fail-closed checks (`tests/test_deployment_config.py`)

CI requires PostgreSQL and Redis; it fails instead of silently substituting SQLite or an in-memory cache. Local tests may use SQLite and an in-memory cache when those services are unavailable.

---

## Design System & Accessibility

The user interface adheres to the design engineering principles in `.agents/skills/` (`better-interface`, `better-typography`, `better-colors`, `better-ui`, `emil-design-eng`):
- **Typography:** System font stack with proportional tabular numerals (`tabular-nums`) for dates, percentages, and metrics.
- **Color Independence:** Status badges combine high-contrast semantic background tokens with SVG icons and explicit textual labels (e.g. `Suitable`, `Caution`, `Unsuitable`, `Historical`).
- **Responsive Layout:** The job board reflows to one column and keeps the seven-day selector scrollable at narrow widths. A visual 320px and 200% zoom check is still needed before claiming full coverage.
- **Keyboard Navigation:** Full focus state rings (`:focus-visible`) and semantic landmark structures (`<header>`, `<nav>`, `<main>`, `<footer>`, `<section>`).
