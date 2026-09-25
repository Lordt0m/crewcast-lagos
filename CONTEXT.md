# CrewCast Lagos

CrewCast helps a small outdoor-service team compare scheduled jobs with a forecast and retain the reasons for each planning recommendation.

## Language

**Team**:
The single outdoor-service business whose manager plans the jobs in the first version.
_Avoid_: tenant, account, organisation

**Site**:
A saved Lagos-area work location with coordinates used to request a forecast. Several jobs may share one site.
_Avoid_: weather station, forecast location

**Job**:
A planned outdoor work window at one site, with a title, local start and end time, and a weather policy.
_Avoid_: task, booking, appointment

**Weather policy**:
The job's recorded caution and stop thresholds for rain probability, precipitation, wind gusts, and apparent temperature. It is a planning preference, not a safety standard.
_Avoid_: safety rule, alert setting

**Forecast snapshot**:
An immutable, normalized set of hourly forecast values for one site and one content version. Its timestamp is the time CrewCast first retrieved that version, not a claim about when the provider issued it.
_Avoid_: live weather, observation

**Sync attempt**:
A recorded attempt to obtain a forecast for a site, whether it succeeds, fails, reuses identical forecast content, or is deferred before a request.
_Avoid_: forecast snapshot, retry

**Recommendation**:
A recorded evaluation of one job window against one forecast snapshot and one weather-policy version, with the values and reasons that produced its status.
_Avoid_: approval, safety clearance, weather warning

**Data state**:
Whether the latest successful retrieval is fresh, stale, or expired under CrewCast's time policy. This is separate from the recommendation's weather status.
_Avoid_: weather status

**Planning status**:
The recommendation's `suitable`, `caution`, or `unsuitable` result when complete, fresh forecast data exists. A missing or expired forecast produces no current planning status.
_Avoid_: safe, unsafe
