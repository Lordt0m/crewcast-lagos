# Product specification — CrewCast Lagos

## Purpose and audience

A dispatcher or owner of a small Lagos maintenance, cleaning, installation, or event setup team needs to review tomorrow's outdoor jobs without juggling a generic weather screen and a separate job list. CrewCast links each job to a site, evaluates forecast conditions during the job window, explains which threshold was crossed, and preserves earlier recommendations so changes are auditable.

This is a synthetic portfolio demonstration and a planning aid. It does not claim real customers, accurate site-level weather observations, or that a job is safe to perform. The manager makes the final operational decision.

The recruiter-visible value is a working background pipeline and a clear recovery story: scheduled synchronization, durable forecast versions, budgeted upstream requests, retries, stale handling, and an explainable decision history.

## First-version scope

- One team and one manager role; local sign-in protects editing and operations controls. Public demo pages may be read-only and contain synthetic jobs only.
- At most 10 active Lagos-area sites. Each site has an explicit name and coordinates; jobs at the same site share forecast retrieval.
- Jobs have a title, site, start and end in `Africa/Lagos`, and a copied weather policy. Keep both original and current policy versions for history. The planning horizon is the next seven local calendar days.
- The default policy is editable by the manager and is copied into a new job. For the synthetic demo, example caution/stop pairs are rain probability 40/70%, precipitation 2/5 mm in an hour, wind gusts 25/40 km/h, and apparent temperature 30/35 °C. These are illustrative product settings, not occupational guidance. Require caution < stop for every metric.
- Open-Meteo is the sole live weather provider for the non-commercial prototype, including its public read-only board. Request only `precipitation_probability`, `precipitation`, `wind_gusts_10m`, and `apparent_temperature`, for seven days and `Africa/Lagos`. Convert valid times to timezone-aware UTC for storage; display Lagos local time. The hourly rain and gust fields describe the preceding hour, while apparent temperature is an instantaneous value. For a job that overlaps an hourly interval, conservatively include that interval; document the approximation in the UI.
- For each complete job window, take the maximum probability, maximum hourly precipitation, maximum gust, and maximum apparent temperature across intersecting hours. A value at or above any stop threshold yields `unsuitable`; otherwise a value at or above any caution threshold yields `caution`; otherwise `suitable`. Record every crossed metric, its value, threshold, unit, and hour. If any required hour or metric is missing, return `unavailable` instead of guessing.
- A successful new snapshot or a policy/job change reevaluates affected jobs. A recommendation is uniquely identified by job revision, policy version, and snapshot; repeating the same inputs creates no duplicate history. The previous recommendation remains visible alongside a new one when the status or reasons change.
- Read views use PostgreSQL as the source of truth and may cache the current response in Redis. Every response includes the data state and last successful retrieval time; a cache hit never changes the stated age.

## Freshness and failure contract

The following are CrewCast policy choices, not Open-Meteo promises:

| Time since last successful retrieval | Data state | Current job view |
| --- | --- | --- |
| 0 to 4 hours | Fresh | Show current recommendation and source time. |
| Over 4 to 12 hours | Stale | Show the last recommendation as historical context, label its age prominently, and require manager review. Do not present a new `suitable` status. |
| Over 12 hours or no complete snapshot | Expired / unavailable | Show no actionable recommendation; explain when a retry is due. |

This age uses the latest successful *retrieval* of the content, even if its payload is identical to an existing snapshot. `generationtime_ms` in the provider response is processing time, not a forecast issue timestamp. The API can map a requested site to a nearby model grid cell; preserve returned grid coordinates for provenance and avoid saying the forecast is an on-site measurement. [Forecast API](https://open-meteo.com/en/docs).

The worker schedules a due-site check every three hours. A timeout, `429`, or `5xx` gets at most two further attempts with bounded exponential backoff and jitter; honor `Retry-After` when present. Malformed data and unsupported schema are recorded as permanent failures until the next scheduled cycle. A simple provider-wide circuit opens after repeated transient failures and permits one probe after cooling off. The UI shows the last success, last failure category, next attempt, and whether the circuit is open. No page request calls Open-Meteo directly.

Use an internal hard cap of 300 outbound provider attempts per Lagos calendar day, enforced atomically in PostgreSQL and including retries and failed calls. The planned maximum is 10 sites × 8 due cycles × 3 attempts = 240; reserve 60 for probes and drift. If the budget is exhausted, defer sync and show why. Open-Meteo's free hosted service currently permits fewer than 10,000 calls/day, 5,000/hour, and 600/minute for non-commercial use; the smaller internal budget is deliberate and should be configurable without removing the published limit checks. [Open-Meteo terms](https://open-meteo.com/en/terms).

## Main journeys

1. Manager signs in, creates a site and job, and sees a pending forecast state until the first successful sync.
2. Scheduler fetches due sites; the manager sees a job list ordered by attention required, with conditions, exact forecast age, and a link to reasons.
3. Manager opens a job to compare current and prior recommendations, each tied to a snapshot, policy version, and evaluated hours.
4. Manager opens Operations to see scheduled runs, attempts, budget consumption, cache state, recent failures, and recovery.
5. A recruiter opens a public read-only board with synthetic jobs evaluated against live Open-Meteo forecasts. A separate, clearly labelled fixture replay shows success → timeout → stale data → successful recovery; it does not mutate shared state or pretend to be live weather. Server-side demo mode disables every state-changing web route for every visitor, including a signed-in manager, while scheduled background sync remains active under the request budget.

## Boundaries

No geocoding, maps, automatic dispatch, push notifications, SMS, employee accounts, customer information, billing, multiple organizations, historical forecast API, alternative weather providers, or commercial operation in the first version. Do not use a forecast to declare work safe. All demonstration names, sites, and jobs are synthetic. Public visitors cannot change jobs, force provider calls, or exhaust the request budget.

## Definition of done

- A manager can create and edit a job; validation rejects an end before start, a window outside the seven-day horizon, and invalid threshold ordering.
- For a complete fixture, evaluations match the documented max-and-threshold rules at boundaries, across partial hours, and across Lagos midnight. Missing data returns `unavailable`.
- Identical successful payloads produce one immutable snapshot version and one recommendation per input version, while each fetch still has its own attempt record and updates retrieval age.
- Two workers racing on the same site cannot commit duplicate versions, overspend the budget, or both run the same due sync. Test with PostgreSQL and Redis, not SQLite-only substitutes.
- `429`, `5xx`, timeout, malformed response, retry exhaustion, open circuit, stale data, expiry, and recovery each have deterministic automated tests and visible UI states.
- Redis loss causes a database-backed read path and a visible but nonfatal cache warning; it never loses snapshots or history.
- Tests use controlled clocks and fixtures and make no live network calls. A separate optional smoke command may test provider connectivity.
- A public demonstration is read-only for every account, uses synthetic jobs with live, time-labelled Open-Meteo data, attributes the provider and explains CrewCast's derived recommendations, identifies fixture replay honestly, and links to source and a short architecture explanation. Verify the scheduled worker fetches live data within the local and provider limits while public page views never trigger provider calls.
- README explains setup, configuration, worker and scheduler startup, seed data, test commands, failure replay, data licence, known limits, and what was actually deployed. No claimed outcome or coverage percentage without measurement.
