# Keep provider access in scheduled workers

Status: accepted for the CrewCast plan.

Only budgeted background workers may call Open-Meteo; Django page requests read PostgreSQL and optionally Redis. This separates a visitor's request rate from upstream calls, permits durable retries and circuit state, and keeps the app useful during provider outages. The trade-off is that a newly created site may briefly show “Waiting for first forecast” and the system needs a scheduler and worker. Calling the provider from page views would seem simpler initially, but makes freshness, budget control, and outage recovery unpredictable under public demo traffic.
