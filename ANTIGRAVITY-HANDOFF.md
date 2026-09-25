# Antigravity handoff — CrewCast Lagos

## Instruction to paste into Antigravity

Open a new CrewCast Lagos application repository. Copy this planning pack into the repository first and read `README.md`, `product-spec.md`, `CONTEXT.md`, `architecture.md`, `interface-brief.md`, `delivery-tickets.md`, and both ADRs before planning code changes. Inspect the new repository's existing instructions and state. Create an implementation plan artifact broken into the numbered tickets, then implement and verify one ticket at a time. Show the owner the plan artifact at the normal Antigravity review point. Keep progress and actual test evidence in the repository; do not claim a ticket is complete before its checks pass.

The source planning pack currently lives at `C:\Users\Lord\Documents\Codex\2026-09-21\employability-programme\outputs\crewcast-lagos`. If Antigravity opens another workspace, copy the entire pack into that repository, including the `.agents/skills/` folder and its MIT notices; a file path from another workspace may not be visible to its agent. Antigravity 2.0, its IDE, and CLI recognize project skills under `<workspace-root>/.agents/skills/`; verify availability there before invoking the named design skills. The product spec and interface brief remain the handoff authority if the skills are unavailable. [Antigravity agent skills](https://antigravity.google/docs/skills/).

## Product to build

CrewCast Lagos is a synthetic, recruiter-visible weather-aware planning aid for a small outdoor-service team. A manager creates Lagos-area sites and jobs. A scheduled worker retrieves live Open-Meteo forecasts in local and public non-commercial demo environments, stores immutable content versions and each fetch attempt, and records explainable recommendations against a versioned job policy. The job board leads with work needing attention and always shows data age. Operations exposes the request budget, last success, failures, retry timing, circuit state, and recovery. The public board is read-only and shows synthetic jobs against live forecast data. A separate, explicitly labelled fixture replay shows an outage and recovery without shared-state mutation. Demo mode disables all state-changing web routes server-side, even for authenticated accounts, while scheduled background sync remains active.

Build with Python/Django, server-rendered HTML, PostgreSQL, Redis, and Celery worker plus Beat. Choose maintained dependency versions when implementing. Keep the provider behind one small, testable interface and the evaluator pure. Page requests must never fetch live weather. The four Open-Meteo hourly fields are precipitation probability, precipitation amount, wind gusts at 10m, and apparent temperature. Use `Africa/Lagos`, a seven-day horizon, and the exact evaluation/freshness rules in the product spec. Do not treat `generationtime_ms` as a forecast issue timestamp. Preserve returned grid cell coordinates separately from the requested site. [Open-Meteo API](https://open-meteo.com/en/docs).

Ayotomiwa's stated purpose is a non-commercial demonstration, not a promotional activity or operational commercial service. Use the free hosted Open-Meteo API for scheduled live forecasts in this prototype, within its published limits. Its terms separately classify promotional activities as commercial; revisit the licence if the project's use changes to marketing, subscriptions, advertising, or real business operations. The free service has no uptime guarantee. Attribute Open-Meteo for live data and CrewCast's derived values, and label fixture replay data clearly. Do not enroll in a paid plan, enter payment details, or claim commercial readiness on the owner's behalf. [Terms](https://open-meteo.com/en/terms), [pricing](https://open-meteo.com/en/pricing).

## Implementation boundaries

Preserve every observable rule in the planning pack. Do not add maps, geocoding, public writes, customer data, staff scheduling, notifications, automatic dispatch, alternative weather APIs, or a separate SPA frontend. Do not change Ayotomiwa's existing portfolio website in this task. Use synthetic seed data and honest labels; do not claim real users, safety approval, measured reliability, or deployment before verifying it.

When an architectural detail remains open, make the smallest maintainable choice and document it. Ask the owner only when a choice would materially change product scope, introduce ongoing cost, require credentials or hosting account control, or conflict with the specifications. A deployment blocker does not prevent completing the local application and reproducible demo.

## Verification and report

Run pure evaluator tests, PostgreSQL/Redis integration and concurrency tests, worker failure/recovery tests, and browser checks for the complete board → detail → operations flow at desktop, 320px, and 200% zoom. Apply the `better-interface` review across accessibility, layout, writing, typography, color, and UI polish to the actual rendered implementation, and use `emil-design-eng` for restrained, responsive interaction details. Fix observed blockers before calling the UI done.

Provide a final execution report with completed ticket numbers, commands and results, any failed or skipped checks, deployment URL if verified, current limitations, and any owner action needed. Include a short evidence-based description suitable for a later portfolio update, but do not edit the portfolio now.

## Current Antigravity workflow note

Official Antigravity documentation describes an [implementation plan artifact](https://antigravity.google/docs/implementation-plan/) for reviewing planned code changes and [artifacts](https://antigravity.google/docs/artifacts/) for progress and review across Antigravity 2.0 and CLI. Use the available planning and review controls in the owner's installed surface; do not depend on an undocumented command or assume the old IDE Agent Manager is the only surface. [Antigravity 2.0 overview](https://antigravity.google/docs/overview).
