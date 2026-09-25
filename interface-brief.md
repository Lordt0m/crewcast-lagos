# Interface brief — CrewCast Lagos

## Direction

Build a calm, fast planning desk for a dispatcher checking jobs before sending a crew out. The page should answer, in order: **What needs my attention? Why? How current is the information?** It should feel like an operational tool, with restrained depth and little decorative motion. The visual source is the supplied [Jakub Krehel](https://github.com/jakubkrehel/skills) and [Emil Kowalski](https://github.com/emilkowalski/skills) skill collections, applied through the project-local `better-interface` companion skills and `emil-design-eng`. They are design principles, not screen templates, so no existing product layout is being copied.

This is a design brief for an app that does not yet exist. A `better-interface` code review, contrast measurement, and rendered-state verdict can happen only after the UI is built.

## Navigation and screen hierarchy

| Screen | Primary question | Primary content | Main action |
| --- | --- | --- | --- |
| Job board | Which jobs need review? | Day picker, source freshness banner, list grouped by `No current recommendation`, `Unsuitable`, `Caution`, then `Suitable`, with local time, site, status text, and top reason. | `Add job` for signed-in manager. |
| Job detail | Why did this status appear or change? | Job window, policy thresholds, worst hourly values, timestamped reasons, retrieval age, and a compact comparison with the prior recommendation. | `Edit job` for manager. |
| Operations | Is the forecast pipeline working? | Last success, next due sync, attempt timeline, budget used, circuit state, cache/worker health, and recovery explanation. | No public force-refresh control. |
| Read-only demo | What does the backend prove? | Synthetic example jobs evaluated with live, timestamped forecasts; a separate, clearly labelled fixture replay of success, timeout, stale state, and recovery; links to architecture and tests. | `View scenario` selector; it changes only the displayed replay. |

On a job card, make the result and reason readable together: `Caution · Rain probability reached 58% during 14:00–15:00`. Follow with `Forecast retrieved 2h 10m ago` in a stable place. Never rely on green, amber, or red alone. Do not show a large generic weather dashboard above the jobs; the job decision is the product.

## Critical states and copy

| State | Interface treatment | Suggested copy |
| --- | --- | --- |
| First sync pending | Neutral inline banner and placeholder in affected job cards. | “Waiting for the first forecast. Jobs will show a planning status after the next sync.” |
| Fresh | Quiet source line near the status. | “Forecast retrieved 2h ago · Open-Meteo” |
| Stale, 4–12h | Persistent caution banner, prior result visibly marked as historical. | “Forecast is 7h old. Review conditions before using the earlier recommendation.” |
| Expired, over 12h | Replace current result with `No current recommendation`; keep history accessible. | “Forecast is too old to guide this job. Next retry: 10:15 WAT.” |
| Provider failure | Operations shows the failure category and next retry; job board retains the correct data state. | “Forecast update timed out. Stored data is shown with its age; retry scheduled for 10:15 WAT.” |
| Budget exhausted | Operations explains the local cap and reset. | “Today’s forecast request budget is used. Updates resume tomorrow after 00:00 WAT.” |
| Missing hour or metric | No fabricated `Suitable` result. | “No recommendation: the forecast does not cover the full job window.” |
| No jobs | Orientation plus one action. | “No jobs planned for this day. Add a job to compare its work window with the forecast.” |
| Form error | Field-level instruction and focus on first failing field. | “Choose an end time after the start time.” |

Use sentence case for headings, labels, and actions; verb-first buttons; calm language for failures. Display `WAT` and the local date on time-sensitive screens, while keeping accessible full timestamps available. Include an always-visible note near recommendation explanations: “Planning signal only. Check current conditions and site requirements before work.” The source attribution must identify Open-Meteo and link to its site; say that values have been evaluated against CrewCast's job policy.

## Layout and type

- Desktop: a readable single main column for the board, with a compact right-side source/operations summary only if it does not push the job list below the first viewport. Job detail can use two columns for conditions and history where both remain legible.
- Mobile: preserve the same reading order, with status and next required action before the forecast numbers. Collapse to one column based on content fit, not a preset device label. Keep actions within safe-area margins and do not hide essential controls under sticky chrome.
- Use a small type scale: one clear page title, descending section headings, normal 16px reading text, and tabular numerals for times, ages, thresholds, and changing counts. Keep mobile inputs at 16px. Let long site names wrap; no critical reason may be irretrievably truncated.
- Group a job's time, site, and weather reason using shared alignment and spacing. Start with roughly twice as much space between jobs as within one job. Use lines only where space cannot distinguish groups. A dense operations table can use separators if needed.

## Color, surfaces, and icons

Begin with one neutral ramp, a deep blue action accent, and semantic green/amber/red status ramps. `Suitable`, `Caution`, and `Unsuitable` also get distinct words and icons. `Stale` is a data-quality state, so it must have its own text treatment and must never masquerade as a fourth weather level. Name component tokens by role (`text-primary`, `surface-raised`, `status-caution`) and measure every rendered foreground/background pair before accepting colors. [WCAG 2.2](https://www.w3.org/TR/wcag/) calls for 4.5:1 contrast on normal text and 3:1 on large text and meaningful non-text indicators; verify actual values in the implementation.

Use subtle surface depth only for interactive or raised pieces. Keep icons from one library, with consistent stroke weight; do not put icons on every label. Weather glyphs may support scanning, but their meaning must be in visible text. Any nested rounded surfaces should have concentric radii so their edges look intentional.

## Interaction and accessibility

Use native links, buttons, form controls, and headings. Give every control a visible label, visible keyboard focus, and a touch target that is comfortable on a phone. Test a complete job creation and inspection path by keyboard and screen reader, at 320px width and 200% zoom. Status updates may be announced politely; errors identify how to recover. Never remove content that a user can reach with only a pointer.

High-frequency board navigation and day selection should respond immediately. A rare drawer or dialog may have a short, interruptible transition that explains where it came from; no animation should delay the decision. Keep each animated state understandable with static text/icon cues and honor `prefers-reduced-motion`. Use hover effects only on devices with hover capability. The first page load should not stagger jobs into view.

## Review checklist for the future implementation

Run a real `better-interface` review over the board → detail → operations flow after all four states (fresh, pending, stale, expired) are implemented. Its six owners are accessibility, layout, writing, typography, colors, and UI polish. Inspect the rendered desktop and narrow layouts, keyboard flow, screen-reader names, contrast, and motion; report only observed findings against the built files. Review the fixture replay separately for honest labelling and no side effects.
