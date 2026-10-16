# CrewCast Lagos

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Outdoor service dispatchers planning jobs in Lagos; visitors evaluating an educational prototype. The user's redesign brief delegates visual and interaction decisions.

## Product Purpose

Compare scheduled job windows with stored forecasts and versioned weather preferences. Show which jobs need review, why, and how current the evidence is.

## Capabilities and Constraints

Django server rendering with progressive TypeScript enhancement. Essential links, forms and content work without JavaScript. Backend owns evaluation, freshness, authorization, caching, retries, budgets and circuit state. Page views never retrieve provider forecasts. Demo mode is read-only. Fresh is at most 4 hours, stale is over 4 through 12 hours, expired is over 12 hours. Favourable stale recommendations are suppressed. The app is a planning aid, never occupational-safety clearance.

## Evidence on Hand

Existing code and tests, live public board, Operations and seven deterministic replay scenarios. Example jobs are synthetic; verified provider retrievals are separate. No customer, testimonial or outcome claims are available.

## Brand Commitments

CrewCast Lagos; a distinctive identity independent of ShelfSum. Explanatory weather and scheduling visuals, clear information hierarchy, expressive typography and considered colour. No endless loops or delayed access.

## Accessibility & Inclusion

Phone, touch, keyboard, reduced motion and JavaScript-disabled use are required by the brief.
