---
name: CrewCast Lagos
description: A weather field bulletin for job windows, forecast evidence and reasons to review.
colors:
  canvas: "#f3f5f2"
  surface-card: "#fff"
  surface-subtle: "#e8eeeb"
  surface-hover: "#e1e9e5"
  text-primary: "#142d39"
  text-secondary: "#3e535b"
  text-muted: "#53656a"
  border: "#aabbb8"
  border-subtle: "#d7dfda"
  accent: "#234fc0"
  accent-hover: "#153a9b"
  accent-surface: "#e8edff"
  sun: "#f2d347"
  suitable-bg: "#dfefe4"
  suitable-text: "#215337"
  suitable-border: "#90b49a"
  caution-bg: "#fff0bd"
  caution-text: "#654600"
  caution-border: "#bda04d"
  unsuitable-bg: "#ffe3dd"
  unsuitable-text: "#8d2d20"
  unsuitable-border: "#d59c8e"
  stale-bg: "#f5e5d6"
  stale-text: "#774519"
  stale-border: "#c1a07e"
  expired-bg: "#e8eceb"
  expired-text: "#3e535b"
  expired-border: "#aabbb8"
typography:
  display:
    fontFamily: '"Barlow Condensed", sans-serif'
    fontSize: "clamp(3.4rem, 6.2vw, 5.8rem)"
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: "-0.02em"
  headline:
    fontFamily: '"Barlow Condensed", sans-serif'
    fontSize: "clamp(2.5rem, 5vw, 4rem)"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.02em"
  title:
    fontFamily: 'Barlow, "Segoe UI", sans-serif'
    fontSize: "1.4rem"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: 'Barlow, "Segoe UI", sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: 'Barlow, "Segoe UI", sans-serif'
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.3
rounded:
  outer: "16px"
  inner: "8px"
  btn: "8px"
  md: "12px"
  sm: "6px"
  badge: "5px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "12": "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface-card}"
    rounded: "{rounded.btn}"
    padding: "10px 18px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.btn}"
    padding: "10px 18px"
  input:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.inner}"
    padding: "10px 12px"
    width: "100%"
  navigation:
    textColor: "#d8e1e3"
    rounded: "{rounded.sm}"
    padding: "10px 14px"
  badge-caution:
    backgroundColor: "{colors.caution-bg}"
    textColor: "{colors.caution-text}"
    rounded: "{rounded.badge}"
    padding: "6px 9px"
    typography: "{typography.label}"
  job-card:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.text-primary}"
    padding: "24px"
  comparison:
    backgroundColor: "{colors.sun}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.outer}"
    padding: "26px"
---

# Design System: CrewCast Lagos

## Overview

**Creative North Star: "Weather field bulletin"**

CrewCast combines the clarity of a dispatch manifest with an explanatory weather bulletin. Ink anchors the frame, signal yellow identifies the example comparison and explanatory notes, and cobalt identifies actions. Condensed, bold headings give the product a clear voice; spacious reading text keeps the evidence usable.

The visual system separates a job's work window, recommendation reason and evidence age without implying occupational-safety clearance. Structural rules, aligned intervals and textual statuses carry meaning. Content remains available before enhancement; motion adds emphasis without delaying access.

**Key Characteristics:**
- Bold condensed headings with a calm reading face.
- Yellow explanation surfaces, ink structure and cobalt actions.
- Whole job records with visible work windows, reasons and evidence age.
- Restrained rounded controls and flat, ruled operational records.
- Optional, cancellable motion with immediate keyboard and reduced-motion behavior.

## Colors

The palette is a cool, pale working surface framed by ink, with yellow for explanation and cobalt for action. The frontmatter records the implemented color values; aliases in the stylesheet resolve to these same primitives. The sidecar's eight-step OKLCH ramps are synthesized swatch previews, not additional implemented color tokens.

### Primary

- **Action Cobalt** (`accent`, `accent-hover`): links, primary buttons, selected sequence outlines and active explanatory emphasis. `accent-surface` provides fine-pointer job-record hover feedback.

### Secondary

- **Signal Yellow** (`sun`): brand location and mark, selected date, ink work-window text, planning heading, synthetic comparison, form/detail signal rules, Operations explanation, footer links and text selection. It is not the same role as the caution status palette.

### Neutral

- **Bulletin Ink** (`text-primary`): main text, header/footer, planning band, work windows, Operations health strip/table headers, comparison time band and threshold-crossing bars.
- **Cool Paper** (`canvas`) and **Card White** (`surface-card`): page and record surfaces.
- **Subtle Wash** (`surface-subtle`, `surface-hover`): secondary containers, table headers, disabled controls and pointer hover feedback.
- **Reading Slate** (`text-secondary`, `text-muted`): explanation, supporting labels and timestamps.
- **Rule Grey** (`border`, `border-subtle`): structural separators and input borders.

Status families each have background, text and border primitives: **Suitable Green**, **Caution Ochre**, **Unsuitable Brick**, **Stale Amber** and **Expired Grey**. Apply their matching triplets; retain visible status wording and the accompanying reason. Badges may also carry an icon. Do not infer a status from color alone.

**The Evidence Rule.** Status color supports the displayed recommendation and freshness language; it never replaces either.

## Typography

**Display Font:** Barlow Condensed, sans-serif. The locally hosted WOFF2 bold face is weight 700.

**Body Font:** Barlow, Segoe UI, sans-serif. The locally hosted WOFF2 regular face is weight 400; current CSS requests 600 and 700 for emphasis, which may be synthesized by the browser.

The pairing is compact and assertive in headings, open and utilitarian in reading text. There is no fixed modular ratio: the hierarchy follows the content roles.

- **Display:** the public introduction uses the frontmatter display role; below the phone breakpoint it becomes `clamp(3.2rem, 12vw, 4.5rem)`.
- **Headline:** default page headings use the headline role. Operations uses `clamp(3rem, 5vw, 4.5rem)`; the planning heading uses 2.5rem, becoming 2.2rem on phones.
- **Title:** default section headings use the title role. Condensed record titles use 1.7rem with 1.1 line-height; job groups and Operations section headings use 2rem; detail-panel and selected-date headings use 1.8rem. Default subheadings use 1.15rem.
- **Body:** the body role is the baseline; paragraphs have a maximum reading measure of 75ch. The introductory paragraph uses 1.16rem with a 42ch measure, becoming 1.05rem on phones.
- **Label:** the label role describes status badges. Supporting text commonly uses 0.875rem; time and table values use tabular numerals. Condensed job-window times are 1.9rem on the board and 1.5rem on phones.

## Layout

The main container is full width up to 1344px, including horizontal padding of 32px, with 40px above and 64px below. Header and footer interiors stop at 1280px. Spacing primitives are a 4px-based scale; component gaps and optical adjustments retain the exact implemented values rather than forcing every measurement onto that scale.

The introductory comparison uses two equal columns and a 56px gap, reduced to 28px at 1000px. Job records use a 190px ink time column with yellow time text and a flexible content column with a 28px gap. The planning heading is an ink band with 22px by 24px padding. Detail uses a 2:1 split with a minimum 260px secondary column. Operations health cells share one continuous ink strip; the budget uses the caution background and retrieval tables use ink header rows. The ink footer closes the frame.

At 1000px and below, detail becomes one column, and the secondary brand badge disappears. At 700px and below, the main container uses 20px horizontal padding, 28px above and 44px below. The introduction stacks, navigation wraps, and whole job records reflow into one column with the window above the content. The seven-day selector retains seven 104px columns in a horizontally scrollable strip. Wide forecast tables retain a 640px minimum width inside labeled, keyboard-focusable scroll regions.

## Elevation & Depth

Depth is primarily flat and structural. Job links form continuous ruled lists with a 2px ink top rule and 1px record separators; fine-pointer hover changes the record background to the cobalt wash. Detail and Operations panels have square edges, 2px ink top rules and no shadow. The main detail signal uses a 6px yellow top rule. Buttons, general cards, form cards and empty states retain the shared shallow shadow: `0 0 0 1px oklch(0 0 0 / 0.06), 0 1px 2px -1px oklch(0 0 0 / 0.06), 0 2px 4px oklch(0 0 0 / 0.04)`.

**The Structural Depth Rule.** Keep operational records, detail and Operations panels flat and ruled; reserve the shared shallow shadow for the implemented controls and rounded containers.

## Shapes

The shape vocabulary pairs restrained rounded containers with straight rules and rectangular work-window bands. General cards and forms use the outer radius; notes, banners and the planning heading use the medium radius; controls use the inner/button radius; status badges use the badge radius. Job records, detail and Operations panels have square edges. The comparison time band has a small 4px radius, and chart bars have 3px top corners. Roundness supports grouping rather than turning every label into a pill.

Focus is a 3px cobalt outline with a 3px offset. The ink header switches focus to yellow. Day choices use an inset offset of -4px; table regions use -3px. Forced-colors mode adds system-color borders to major controls and records and a Highlight outline to selected navigation.

## Components

### Buttons

Direct, compact actions use the frontmatter primary and secondary variants, minimum height 46px, 1rem text and weight 600. Pointer hover changes cobalt to its deeper value or white to the hover wash; hover styling is restricted to fine, hover-capable pointers. Disabled buttons use the subtle wash, muted text, no shadow and a not-allowed cursor. Comparison replay is a smaller 42px minimum-height secondary control on a pale yellow background.

Fine-pointer press feedback scales to 0.96 over 150ms with the ease-out curve and releases over 100ms. Touch and reduced-motion interactions skip this transform. Keyboard input cancels motion and clears press state; button activation itself is never delayed.

### Inputs / Fields

White native fields use a 1px Rule Grey border, inner radius, 46px minimum height and the frontmatter padding. Labels are weight 600; help and error messages use 0.875rem, with errors in Unsuitable Brick. Disabled text inputs use the subtle wash. Focus uses the shared visible outline. Form cards are centered, stop at 640px and use 28px padding with a 6px yellow top rule and condensed headings.

### Navigation

The ink header contains a yellow weather mark, brand text and wrapping links with a 44px minimum height. Active links have a lighter ink background and yellow text. Day navigation use ruled grids, visible labels and native links with current-state attributes. Selected days use yellow and ink. Dates use condensed 1.8rem type; weekday labels are uppercase with .04em tracking. Retain native navigation and visible current state.

Enhanced date selection replaces only the planning board with newly requested server HTML. It preserves the date strip's viewport position and horizontal scroll and returns keyboard focus to the selected date. Requests use no-store and never retrieve provider forecasts or maintain a client forecast cache. A newer selection aborts the older request, with a generation check guarding commits. Current jobs stay visible while loading; inline status and a full-page retry link explain failure. Back/forward navigation reloads the appropriate board without pushing another history entry. Native date links retain the `#planning` anchor and work without enhancement; modified clicks keep their browser behavior.

### Status badges and banners

Badges use the frontmatter label typography and compact radius, with 1px borders. They are display labels rather than action chips. Banners use 18px by 20px padding, a 12px radius, a strong summary and supporting text. Freshness and example labels stays visible alongside the palette.

### Job records / Containers

An entire job record is one link. It holds the title/site, status, work window, primary reason, retrieval age and detail cue. Use the frontmatter geometry, flat ruled grouping and responsive whole-record reflow. Ink work-window bands use 16px padding, becoming 12px on phones. General cards use the outer radius; flat detail panels use 24px padding, becoming 20px on phones. The primary signal window grows with `clamp(2rem, 4vw, 3rem)` and a 24ch maximum measure.

### Window comparison / Replay sequence

The yellow comparison joins a planned window, four labeled rain intervals, threshold and reason. Percentages and interval labels remain readable alongside the bars. Replay explanations use ordered, labeled stages and native data tables where appropriate; no explanation is hidden until animation completes.

The introductory entrance is eligible only on a first unqualified visit in the session: 480ms opacity/12px vertical motion with 100ms stagger and the ease-out curve. Query or hash navigation does not trigger it. Reduced motion, a reported device with at most two logical processors, Save-Data, or a reported slow-2g/2g/3g connection skips the entrance. A replay highlights one existing step every 650ms; active steps receive a cobalt outline and a 3px rise. A second activation settles the current sequence, and activations within 1200ms of the prior start also settle. Timer cancellation and a generation guard prevent obsolete callbacks from reviving a finished sequence. Keyboard activation and reduced-motion activation settle immediately. Any keydown, reduced-motion preference change, hidden document or page exit cancels entrances and finishes sequences. All text stays available; replay controls are revealed only after enhancement, and polite status text announces progress/completion.

## Do's and Don'ts

### Do:

- Do pair status colors with visible wording, reasons and evidence age.
- Do use Barlow Condensed for expressive headings and work windows, and Barlow for reading.
- Do preserve native links, forms, visible focus and labeled scroll regions.
- Do keep explanations available before, during and after optional motion.
- Do reflow entire job records on phones while retaining their information order.

### Don't:

- Don't present a planning recommendation as occupational-safety clearance.
- Don't blend synthetic examples with retrieved forecast evidence.
- Don't turn display status badges into unexplained action chips.
- Don't loop motion, delay access or restart a sequence when its replay is activated again while running.
- Don't replace the shallow structural depth with large floating shadows.
