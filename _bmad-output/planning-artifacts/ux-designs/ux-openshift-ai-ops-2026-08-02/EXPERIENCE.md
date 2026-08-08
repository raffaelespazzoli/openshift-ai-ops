---
name: OpenShift AI Ops
status: final
created: 2026-08-02
updated: 2026-08-02
sources:
  - prd: ../prds/prd-openshift-ai-ops-2026-08-02/prd.md
---

# OpenShift AI Ops — Experience Spine

## Foundation

Single-surface responsive web. PatternFly React on the standard OpenShift Console frontend stack (React + TypeScript + PatternFly). The component library does most of the work; the standalone app replicates the Console shell (masthead + sidebar) so that migrating to a Console dynamic plugin requires re-parenting components, not redesigning them. `DESIGN.md` is the visual identity reference; this spine is the experience. Single-cluster per deployment; each instance serves one OpenShift cluster.

## Information Architecture

| Surface | Reached from | Purpose |
|---|---|---|
| Incidents | App open (default) / nav item | Firing alerts grouped by Root-Cause Event; toggle to Resolved (configurable time window) |
| Incident Detail | Click alert row in Incidents | Full-page pipeline view: Triage → Diagnosis → Skeptic → Remediation → Execution → Outcome |
| Statistics | Nav item | Operational pulse + reporting: alerts, diagnoses, resolutions over time; MTTR |

Navigation is a vertical left sidebar matching the OpenShift Console pattern. Two nav items: **Incidents** (with NotificationBadge showing count of items awaiting approval) and **Statistics**. Incident Detail is a full-page drill-down with breadcrumb navigation back to Incidents.

→ Composition reference: `mockups/incidents-list.html`, `mockups/incident-detail.html`, `mockups/statistics.html`. Spine wins on conflict.

## Voice and Tone

Microcopy. Brand voice and aesthetic posture live in `DESIGN.md`.

| Do | Don't |
|---|---|
| "3 alerts firing" | "⚠️ Alert! 3 critical issues detected!" |
| "Diagnosis complete. Root cause: node/memory-pressure" | "We found the problem!" |
| "Awaiting approval" | "Action required! Please review immediately" |
| "Resolved in 3m 42s" | "Great job! Issue fixed ✓" |
| "No active alerts" | "All clear! 🎉 Nothing to worry about" |
| "Fast-path: matched case #4271 (98% similarity)" | "AI automatically detected a known pattern" |
| Factual. Short. Status-first. | Encouraging, celebratory, urgent, or anthropomorphizing the AI |

## Component Patterns

Behavioral. Visual specs live in `DESIGN.md.Components` (or in PatternFly defaults, when inherited).

| Component | PatternFly mapping | Behavioral rules |
|---|---|---|
| Incident list | `DataList` (expandable) | RCE group headers are expandable rows; collapsed by default. Header shows: RCE label, correlated alert count badge, highest severity Label, time since first alert. Expand reveals individual alert rows. Click any alert row → full-page detail. |
| Firing/Resolved toggle | `ToggleGroup` in `Toolbar` | Two states: Firing (default), Resolved. Resolved adds a time-range dropdown (last 1h, 6h, 24h, 7d — configurable). Toggle persists in URL query params. |
| Severity filter | `Select` (checkbox variant) in `Toolbar` | Multi-select: critical, warning, info. Default: all selected. Filters visible RCE groups and individual alerts. Persists in URL query params. |
| Pipeline visualization | `ProgressStepper` (horizontal, center-aligned) | Six stages. Each stage shows icon + label + state (completed/active/awaiting/failed/skipped). Click a stage to expand its content panel below. Only one stage expanded at a time. Active stage auto-expands on page load. |
| Stage content panel | `DescriptionList` + `Card` | Renders below the pipeline. Content varies per stage (see Stage Content below). Clean grid layout. Collapses to stacked on narrow viewports. |
| Approval action | `Button` (primary) + `Button` (secondary/danger) | Approve (primary, green) and Reject (danger) in the Remediation stage content when state is `awaiting`. Single-click action — no confirmation modal for standard blast radius. |
| Confidence badge | `Label` (compact) | Three tiers: high (success), medium (warning), low (danger). Shown on dry-run results and diagnosis confidence. |
| Fast-path badge | `Label` (info, compact) | "Fast-Path" text, info variant. Shown in incident list row and detail view breadcrumb. |
| Nav approval badge | `NotificationBadge` | Inline in "Incidents" nav item. Shows count of items in `awaiting` state. Hidden when count is 0. |
| Breadcrumb | `Breadcrumb` | Shown on Detail view: "Incidents > {Alert Name}". Click "Incidents" returns to list. Preserves filter state (Firing/Resolved, severity, time range). |
| Stats cards | `Card` (compact) | Top row of Statistics view. Five cards: total incidents, auto-resolved %, success/failure ratio, MTTR, fast-path hit rate. Each shows current value + trend indicator (up/down/flat). |
| Stats charts | PatternFly Charts (line) | Time-series: alerts over time, diagnoses over time, resolutions over time. Line charts with time-range selector (day/week/month). MTTR as a separate area chart. |
| Empty state | `EmptyState` | "No active alerts." Icon: check-circle (success). No call-to-action — this is the desired state. |
| Loading | `Skeleton` | Matches expected layout shape. Used for initial page load and async pipeline stage data. |

### Stage Content (expanded panel per pipeline stage)

| Stage | Content |
|---|---|
| Triage | Alert payload summary, correlation reasoning (which alerts grouped and why), priority score |
| Diagnosis | Structured diagnosis object: root-cause code (as `Label`), causal chain (ordered list), affected resources (resource list), evidence artifacts (collapsible section with log lines / metric values / resource states), agent conversation summary (prose paragraph), confidence score (`Label`) |
| Skeptic | Challenge summary (what the skeptic probed), response summary (how the diagnosis held or adapted), stability verdict (pass/fail with reasoning) |
| Remediation | Plan steps (ordered list), blast radius (`Label`: workload/namespace/node/cluster), rollback plan (collapsible), dry-run confidence badge, preconditions list. When `awaiting`: Approve/Reject buttons prominent at top. |
| Execution | Execution log (timestamped steps), MCP Server calls made, duration, current status (running/completed/failed) |
| Outcome | Resolution status (alert resolved: yes/no), time to resolution, post-remediation verification results, case record link |

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| Cold app load | Incidents | PatternFly `Skeleton` rows (6–8) matching DataList layout. Resolves on data. |
| No firing alerts | Incidents | `EmptyState`: icon check-circle (success), "No active alerts." No action button. |
| Alert storm (many RCEs) | Incidents | List renders all RCE groups collapsed. Highest-severity groups sort to top. No pagination in v1 — scroll. `[ASSUMPTION: alert storms produce < 50 RCE groups]` |
| Pipeline in progress | Detail | Active stage shows spinner icon. Stages after active show default (grey, no icon). Auto-refresh every 5s while any stage is `active`. |
| Awaiting approval | Detail (Remediation stage) | Remediation stage icon is `pending` (warning). Stage auto-expands. Approve/Reject buttons are the first element in the panel. |
| Fast-path resolved | Detail | Triage and Outcome stages show `completed`. Diagnosis/Skeptic/Remediation stages show `skipped` (greyed). "Fast-Path" label in page header. |
| Diagnosis failed (skeptic rejected) | Detail | Diagnosis stage shows `failed`. If re-challenged, a second pass renders below the first (versioned). |
| Remediation failed | Detail | Execution stage shows `failed`. Outcome stage shows alert-not-resolved. Rollback action available. |
| LLM unavailable | Detail | Diagnosis stage shows `failed` with message: "Diagnosis unavailable — LLM unreachable." If fast-path match exists, fast-path badge appears with option to proceed. |
| Statistics empty | Statistics | Cards show "—" for values. Charts show empty state: "No data for this time range." |
| Statistics loading | Statistics | Cards show `Skeleton`. Charts show PatternFly chart skeleton pattern. |
| API error | All surfaces | PatternFly `EmptyState` with danger icon: "Unable to reach the API." Retry button. No auto-retry to avoid masking persistent failures. Toast variant for transient errors that self-recover. |

## Interaction Primitives

**Mouse-primary.** The audience is SREs on laptops at various alertness levels. Mouse is primary; keyboard shortcuts are a power-user layer, not a requirement.

- **Click alert row** → navigate to detail (full-page)
- **Click RCE group header** → expand/collapse alert group (no navigation)
- **Click pipeline stage** → expand stage content panel (accordion — one open at a time)
- **Click Approve/Reject** → single-click action, no modal confirmation for standard blast radius
- **Toggle Firing/Resolved** → filter switch, URL-persisted
- **Time-range selector** → dropdown in toolbar (Resolved view) and Statistics view

**Keyboard layer (power users):**

- `j` / `k` — move through incident list rows
- `Enter` — open selected incident detail
- `Backspace` or `Esc` — return to Incidents list from detail
- `1`–`6` — jump to pipeline stage by position in detail view
- `a` — approve (when Remediation stage is awaiting and expanded)

**Banned everywhere:** infinite scroll (no pagination either in v1 — list renders fully), auto-refresh that causes layout shift, modal confirmations for routine actions, hover-only affordances.

## Accessibility Floor

Behavioral. Visual contrast lives in `DESIGN.md` (inherits PatternFly's WCAG AA-compliant tokens).

- WCAG 2.2 AA across the responsive web surface.
- PatternFly components provide baseline accessibility out of the box; no degradation permitted from customization.
- Pipeline stage states communicated via `aria-label` (not color alone): "Diagnosis: completed", "Remediation: awaiting approval".
- DataList expansion state announced: "Root-Cause Event: etcd fsync latency, 3 correlated alerts, collapsed. Activate to expand."
- Approve/Reject buttons include `aria-describedby` linking to the remediation plan summary — screen reader users get context before acting.
- Keyboard navigation of pipeline stages uses arrow keys (left/right) per PatternFly ProgressStepper accessibility pattern.
- Focus management: navigating to detail view moves focus to the breadcrumb; returning to list restores focus to the previously selected row.
- Statistics charts include `aria-label` with a text summary of the data (e.g., "Line chart: 23 alerts over the last 7 days, peak on Tuesday").

## Key Flows

### Flow 1 — 2am page response (Karim, on-call SRE, Tuesday 2:07am)

1. Karim's phone buzzes — PagerDuty wakes him. Alert: `KubePersistentVolumeStuckPending`.
2. He opens his laptop, navigates to the AI Ops bookmark. Dark mode greets him — no flash of white.
3. Incidents view loads. One RCE group at the top: "PVC stuck pending (1 alert)" with a severity `warning` label. The nav shows "Incidents (1)" — awaiting his approval.
4. He clicks the alert row. Detail view loads. Breadcrumb: Incidents > KubePersistentVolumeStuckPending.
5. The horizontal pipeline shows: Triage ✓ → Diagnosis ✓ → Skeptic ✓ → **Remediation** (⏳ awaiting) → Execution → Outcome.
6. Remediation stage is auto-expanded. He sees: "Patch StorageClass default-sc to set volumeBindingMode: WaitForFirstConsumer." Blast radius: `namespace`. Dry-run confidence: **high** (green badge). Rollback: "Revert StorageClass patch." Approve / Reject buttons at the top.
7. **Climax:** He clicks Approve. The stage transitions to `completed`, Execution goes `active` with a spinner. Fifteen seconds later, Execution completes, Outcome shows: "Alert resolved. Time to resolution: 3m 42s." The nav badge disappears.
8. He closes the laptop and goes back to sleep.

Failure: LLM was unreachable during diagnosis. Karim sees Diagnosis stage as `failed`: "Diagnosis unavailable — LLM unreachable." Below: "Fast-path match: Case #1847 (94% similarity). Proceed with fast-path?" He clicks proceed; pipeline skips to Remediation with the proven plan.

### Flow 2 — Weekly review (Marco, ops team lead, Monday 10am)

1. Marco opens AI Ops and clicks Statistics in the sidebar.
2. Four summary cards across the top: **23** incidents this week, **78%** auto-resolved, **91%** success rate, **4m 12s** mean time to resolution, **34%** fast-path hit rate. All show green up-trend arrows compared to last week.
3. He switches the time-range to "Last 30 days." Charts update: alert volume is declining (fewer recurring issues), MTTR is dropping (learning store growing), fast-path rate is climbing.
4. **Climax:** Marco exports the Statistics view as a screenshot for the monthly ops review. The data tells a clear story without him having to narrate: the tool is working, incidents are being handled faster, and fewer are requiring human intervention.

Failure: No data for the selected range (new deployment). Cards show "—", charts show "No data for this time range." No error state — this is normal for a fresh install.

### Flow 3 — Alert storm correlation (Priya, platform team lead, Wednesday afternoon)

1. A cluster upgrade triggers a cascade: 8 alerts fire within 90 seconds. Priya's monitoring Slack channel lights up.
2. She opens AI Ops. Incidents view shows 2 RCE groups (not 8 rows): "etcd fsync latency (5 alerts)" and "API server latency (3 alerts)." The system correlated them by temporal proximity and shared component labels.
3. She expands the first RCE group to see the individual alerts: etcdHighFsyncDurations, etcdSlowDiskIO, etcdBackendCommitDuration, etcdNoLeader, etcdGRPCRequestsSlow. All critical.
4. She clicks etcdHighFsyncDurations. The pipeline is still processing: Triage ✓ → **Diagnosis** (🔄 active). The system is reasoning.
5. She waits. Thirty seconds later, Diagnosis completes and Skeptic activates. Another 10 seconds: Skeptic passes, Remediation generates a plan.
6. **Climax:** The nav badge appears: "Incidents (1)". The pipeline shows Remediation awaiting. The plan: "Cordon node worker-3 (hosting etcd member with degraded disk), drain workloads, verify etcd cluster health." Blast radius: `node`. She reviews, approves. The 5 correlated alerts begin resolving one by one as the fix propagates.

Failure: Skeptic rejects the first diagnosis (the root cause was actually a different node). Diagnosis stage shows `failed`, then re-runs. A second Diagnosis attempt appears in the panel (versioned). This time the Skeptic passes. Pipeline continues.
