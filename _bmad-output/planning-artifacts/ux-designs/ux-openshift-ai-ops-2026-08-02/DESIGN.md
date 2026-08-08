---
name: OpenShift AI Ops
description: Alert-driven AI operations console for OpenShift clusters. PatternFly-based; this DESIGN.md specifies the brand-layer delta only.
status: final
created: 2026-08-02
updated: 2026-08-02
sources:
  - prd: ../prds/prd-openshift-ai-ops-2026-08-02/prd.md
colors:
  # PatternFly's global palette is inherited wholesale. Only brand-specific
  # semantic tokens are defined here. Status colors (danger, warning, success,
  # info) inherit from PatternFly --pf-t--global--color--status--*.
  pipeline-completed: '--pf-t--global--color--status--success--default'
  pipeline-active: '--pf-t--global--color--status--info--default'
  pipeline-awaiting: '--pf-t--global--color--status--warning--default'
  pipeline-failed: '--pf-t--global--color--status--danger--default'
  pipeline-skipped: '--pf-t--global--color--disabled--on-disabled'
  confidence-high: '--pf-t--global--color--status--success--default'
  confidence-medium: '--pf-t--global--color--status--warning--default'
  confidence-low: '--pf-t--global--color--status--danger--default'
  fast-path-badge: '--pf-t--global--color--status--info--default'
  nav-badge: '--pf-t--global--color--status--warning--default'
typography:
  # PatternFly's type ramp inherited. No overrides — the tool reads like the
  # Console, not like a branded product.
  note: 'Inherits PatternFly type tokens: --pf-t--global--font--*. No brand override.'
rounded:
  note: 'Inherits PatternFly border-radius tokens. No override.'
spacing:
  note: 'Inherits PatternFly spacer tokens: --pf-t--global--spacer--*. No override.'
components:
  pipeline-step-completed:
    icon: 'check-circle'
    color: '{colors.pipeline-completed}'
    variant: 'success'
  pipeline-step-active:
    icon: 'in-progress'
    color: '{colors.pipeline-active}'
    variant: 'info'
  pipeline-step-awaiting:
    icon: 'pending'
    color: '{colors.pipeline-awaiting}'
    variant: 'warning'
  pipeline-step-failed:
    icon: 'exclamation-circle'
    color: '{colors.pipeline-failed}'
    variant: 'danger'
  pipeline-step-skipped:
    icon: 'minus-circle'
    color: '{colors.pipeline-skipped}'
    variant: 'custom'
  confidence-badge:
    background: 'dynamic — {colors.confidence-high} | {colors.confidence-medium} | {colors.confidence-low}'
    foreground: '--pf-t--global--text--color--on-status--on-{variant}'
  nav-approval-badge:
    background: '{colors.nav-badge}'
    foreground: '--pf-t--global--text--color--on-status--on-warning'
---

## Brand & Style

OpenShift AI Ops is a clinical operations console. It handles alerts so the SRE doesn't have to hold the full diagnostic chain in their head. The visual language is deliberately understated — the product recedes so the data advances. No urgency theatrics, no red-pulsing alarms. An SRE opening this at 2am sees a calm, structured surface that tells them exactly what's happening and what (if anything) needs their judgment.

The tool inherits PatternFly wholesale. This is not a branded consumer product — it is infrastructure tooling that will eventually embed inside the OpenShift Console as a dynamic plugin. Every visual decision must remain compatible with that migration. DESIGN.md specifies only the semantic tokens that PatternFly doesn't already provide (pipeline step states, confidence scoring, fast-path badging) and codifies how standard PatternFly patterns are used.

## Colors

PatternFly's status color system is the foundation. No custom hue is introduced.

- **Status colors** (`danger`, `warning`, `success`, `info`) are used exclusively for their semantic meaning — never decoratively. `danger` = critical severity or pipeline failure. `warning` = medium severity or awaiting human action. `success` = resolved or completed. `info` = active processing or informational.
- **Pipeline semantic tokens** map one-to-one to PatternFly status variants. This ensures the ProgressStepper reads identically in the standalone app and the future Console plugin.
- **Confidence scoring** uses a three-tier scheme: high (success green), medium (warning gold), low (danger red). Rendered as PatternFly `Label` components with the appropriate color variant.
- **Navigation badge** uses the `warning` variant — attention-requesting but not alarming.
- **Dark mode** is handled entirely by PatternFly's built-in dark theme toggle. No custom dark-mode tokens needed because all semantic tokens reference PatternFly CSS custom properties that auto-resolve per mode.

Avoid: custom hex values, gradient surfaces, brand colors beyond PatternFly's palette, using `danger` red for anything other than genuine severity-critical or pipeline-failed states.

## Typography

PatternFly's type ramp inherited as-is. Title sizes follow PatternFly heading tokens (`--pf-t--global--font--size--heading--*`). Body, label, and helper text use PatternFly's defaults. The tool should feel like part of the OpenShift Console — not a separate branded product.

No display or serif typography. No brand-specific type moments. The content carries the hierarchy, not the typeface.

## Layout & Spacing

PatternFly's spacer scale inherited. Page structure uses PatternFly `Page`, `PageSection`, `PageSidebar` components matching the Console shell.

- **Max content width:** unconstrained — data tables and pipeline visualizations benefit from full viewport width.
- **Page layout:** horizontal masthead (top) + vertical navigation (left sidebar). Matches OpenShift Console shell to enable seamless plugin migration.
- **Grid:** PatternFly's responsive grid (`Grid`, `GridItem`) for the Statistics view. Single-column stacking below `lg` breakpoint.
- **Breakpoints:** PatternFly defaults (`sm` 576px, `md` 768px, `lg` 992px, `xl` 1200px, `2xl` 1450px). Desktop-first; adaptive for future mobile without mobile-specific overrides.

## Elevation & Depth

Inherited from PatternFly. Cards use PatternFly's default raised surface. No additional shadow layers. The clinical posture means flat surfaces with clear borders, not depth-simulated stacking.

## Shapes

PatternFly's border-radius tokens inherited. No tighter or looser corners — maintain Console parity.

## Components

All components are PatternFly React components, used as documented. No custom components in v1. Brand-layer-specific usage:

- **ProgressStepper** — The pipeline visualization. Each step uses the semantic `variant` from the component tokens above. Horizontal orientation. `isCenterAligned` for the full-page detail view.
- **Label** — Severity badges (`danger`, `warning`, `info`), confidence scores, fast-path indicator. Compact variant for inline use in table rows.
- **NotificationBadge** — The navigation approval counter. Placed inline in the nav item text.
- **DataList** — The incident list with expandable RCE group headers. Expandable rows for alert grouping under Root-Cause Events.
- **DescriptionList** — Structured display of diagnosis objects, remediation plans, and evidence artifacts inside expanded pipeline stages.
- **Card** — Summary statistics tiles on the Statistics view.
- **Toolbar** — Filter controls (Firing/Resolved toggle, time-range selector) above the incident list.
- **Breadcrumb** — Full-page navigation context on the detail view (Incidents > Alert Name).
- **ToggleGroup** — The Firing/Resolved toggle in the Incidents toolbar. Two items, persistent selection.
- **Select** (checkbox variant) — Multi-select severity filter in the Incidents toolbar.
- **Button** — Primary (approve), danger (reject), and link variants used for actions. PatternFly defaults, no visual override.
- **PatternFly Charts** (line, area) — Time-series visualizations on the Statistics view. Line for alerts/diagnoses/resolutions; area for MTTR. PatternFly chart color ramp inherited.
- **EmptyState** — Used when no alerts are firing (the good state).
- **Skeleton** — Loading states for async pipeline data.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use PatternFly status colors only for their semantic meaning | Repurpose `danger` for visual emphasis without actual danger |
| Let PatternFly handle dark/light mode entirely via theme toggle | Create custom dark-mode overrides or hardcode colors |
| Match the Console shell layout (masthead + sidebar) | Invent a novel navigation pattern |
| Keep density moderate — SREs scan lists quickly | Over-space for aesthetics at the cost of scan speed |
| Use `Label` compact variant for inline metadata | Use full-size badges that interrupt reading flow |
| Render the pipeline as a ProgressStepper with clear stage states | Animate stages or pulse active states aggressively |
| Default to dark mode (SRE late-night context) but support both | Force dark mode without a toggle |
