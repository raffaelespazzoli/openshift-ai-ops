# Spine Pair Review — OpenShift AI Ops

## Overall verdict

A lean, well-structured pair. Both spines have all canonical sections in order, sources resolve, protagonist names are verbatim from the PRD, and the PatternFly-only token strategy is sound. The main mechanical gaps are (a) four standard PatternFly components used in EXPERIENCE.md without corresponding DESIGN.md visual-spec rows, (b) missing API-error and detail-view-loading states, and (c) Breadcrumb absent from the EXPERIENCE.md Component Patterns table. No critical findings; three medium-severity gaps to close before implementation.

## 1. Flow coverage — strong

Extracted FR-21 (Standalone Web Application) and FR-22 (Summary Dashboard) from the PRD. All FR-21 consequences (incident list with filtering, incident detail with diagnosis/skeptic/remediation/dry-run/execution, approval workflow, Console independence) and FR-22 consequences (aggregate metrics, time-range filtering, read-only) are exercised across the three Key Flows. Each flow has a named protagonist, numbered steps, a climax beat, and a failure path.

| PRD item | Key Flow | Protagonist | Climax | Failure path |
|---|---|---|---|---|
| UJ-1 / FR-21 | Flow 1 — 2am page response | Karim | Approve click (step 7) | LLM unreachable → fast-path fallback |
| UJ-3 / FR-22 | Flow 2 — Weekly review | Marco | Export screenshot (step 4) | Empty data on fresh install |
| FR-21 (storm) | Flow 3 — Alert storm correlation | Priya | Approve correlated fix (step 6) | Skeptic rejects → re-diagnosis |

### Findings

No misses.

## 2. Token completeness — strong

All 10 color tokens defined in DESIGN.md frontmatter. All `{colors.*}` references inside the `components` YAML block resolve to defined tokens. All `--pf-t--global--*` references are valid PatternFly CSS custom properties and correctly delegate resolution to the design system.

### Findings

- **low** `fast-path-badge` color token defined (DESIGN.md frontmatter line 21) but never referenced by any component entry in the `components` YAML block. The prose Components section describes the fast-path badge as a `Label` with `info` variant, but the frontmatter component map has no `fast-path-badge` entry consuming `{colors.fast-path-badge}`. *Fix:* Add a `fast-path-badge` component entry to the frontmatter, or remove the orphan color token if the info variant alone is sufficient.
- **low** `confidence-badge.foreground` uses `--pf-t--global--text--color--on-status--on-{variant}` (DESIGN.md frontmatter line 54). The `{variant}` placeholder is a dynamic interpolation marker, not a defined token path — semantically clear but breaks the `{path.to.token}` convention. *Fix:* Add a comment clarifying the interpolation, or enumerate the three concrete values.

## 3. Component coverage — adequate

Extracted 15 distinct component names across both files. Nine components have both a visual-spec row (DESIGN.md) and a behavioral-spec row (EXPERIENCE.md). Four components referenced in EXPERIENCE.md lack DESIGN.md visual-spec rows. One DESIGN.md component lacks an EXPERIENCE.md behavioral-spec row.

### Findings

- **medium** `Breadcrumb` has a DESIGN.md visual-spec row (prose Components section, line 112) but no row in EXPERIENCE.md Component Patterns table. Breadcrumb behavior is mentioned in IA and Key Flows but without formal behavioral rules (e.g., truncation for deep paths, active-segment styling). *Fix:* Add a Breadcrumb row to the Component Patterns table with behavioral rules.
- **medium** `ToggleGroup`, `Select` (checkbox variant), `Button`, and `PatternFly Charts` are named in EXPERIENCE.md Component Patterns but have no corresponding rows in DESIGN.md Components. These are standard PatternFly components with no brand-layer delta, which is the stated DESIGN.md policy ("No custom components in v1"), but the rubric requires a visual-spec row per component. *Fix:* Add a brief note in DESIGN.md Components that explicitly lists PatternFly components used as-is with no brand-layer override, or add minimal rows confirming "inherited — no override."

## 4. State coverage — adequate

Walked three IA surfaces (Incidents, Incident Detail, Statistics). Domain-specific states are well-covered: pipeline-in-progress, awaiting-approval, fast-path, diagnosis-failed, remediation-failed, LLM-unavailable, alert-storm, and both empty/loading variants for Statistics are all specified.

### Findings

- **medium** No API/backend error state for any surface. If the REST API is unreachable or returns 500, the user experience is unspecified. Applies to Incidents, Incident Detail, and Statistics. *Fix:* Add a global error state row in State Patterns covering API-unreachable / server-error treatment (e.g., PatternFly `EmptyState` with danger icon and retry action).
- **low** Incident Detail has no explicit cold-load / loading state. "Cold app load" in State Patterns (line 77) specifies only the Incidents surface. The detail view loads async pipeline data (acknowledged by the Skeleton entry) but the initial page-load skeleton is not specified. *Fix:* Add a "Cold detail load" row specifying the detail-view skeleton shape (breadcrumb + pipeline stepper skeleton + empty content panel).

## 5. Visual reference coverage — expected gap

No `mockups/`, `wireframes/`, or `imports/` directories exist. Only three files in the workspace: `DESIGN.md`, `EXPERIENCE.md`, `.memlog.md`. EXPERIENCE.md IA section (line 26) references `mockups/incidents-list.html`, `mockups/incident-detail.html`, `mockups/statistics.html` — these are forward references to files that haven't been created yet. This is expected and noted.

### Findings

No actionable findings. Mockup creation is a separate downstream task.

## 6. Bloat & overspecification — strong

No pixel specs — all measurements defer to PatternFly tokens. No persona definitions restated (protagonist names only). FRs referenced by ID, not restated. Tables used where appropriate (Component Patterns, State Patterns, IA, Do's/Don'ts). Key Flows are narrative but serve their purpose — they demonstrate UX choreography, not requirements restatement. DESIGN.md Brand & Style section is three paragraphs; no padding.

### Findings

No findings.

## 7. Inheritance discipline — adequate

Sources frontmatter resolves in both files (`../prds/prd-openshift-ai-ops-2026-08-02/prd.md` — path exists). Protagonist names verbatim from PRD (Karim/Marco/Priya with roles). Nine of thirteen component names are identical across both files. EXPERIENCE.md defers to "DESIGN.md.Components" for visual specs and uses the same PatternFly variant vocabulary (success/warning/danger/info).

### Findings

- **medium** Four components in EXPERIENCE.md Component Patterns (`ToggleGroup`, `Select`, `Button`, `PatternFly Charts`) have no corresponding entry in DESIGN.md. This breaks the "component names identical across all sections in both files" check. These are standard PatternFly components, but inheritance discipline requires at least an acknowledgment in DESIGN.md. *Fix:* Same as §3 — add explicit "used as-is" entries or a catch-all note.
- **low** EXPERIENCE.md token cross-references to DESIGN.md use semantic descriptions ("success green," "warning gold," "danger red") rather than formal token paths (`{colors.confidence-high}`, etc.). This is understandable for a behavioral spine but loosens the coupling. *Fix:* Consider adding parenthetical token names on first use in EXPERIENCE.md (e.g., "high — success green (`{colors.confidence-high}`)").

## 8. Shape fit — strong

**DESIGN.md** sections in canonical order: Brand & Style → Colors → Typography → Layout & Spacing → Elevation & Depth → Shapes → Components → Do's and Don'ts. All present.

**EXPERIENCE.md** required defaults all present: Foundation → Information Architecture → Voice and Tone → Component Patterns → State Patterns → Interaction Primitives → Accessibility Floor → Key Flows. All present.

### Findings

No findings.

## Mechanical notes

- **Frontmatter completeness:** Both files have `name`, `status`, `created`, `updated`, `sources`. DESIGN.md additionally has `colors`, `typography`, `rounded`, `spacing`, `components` — all populated. EXPERIENCE.md frontmatter is minimal (no token definitions), which is correct for a behavioral spine.
- **Cross-ref integrity:** EXPERIENCE.md references `DESIGN.md` and `DESIGN.md.Components` — both valid. Mockup references (`mockups/*.html`) point to nonexistent files (expected).
- **Name consistency:** "Root-Cause Event" / "RCE" used consistently in both files and matches PRD terminology. Pipeline stage names (Triage, Diagnosis, Skeptic, Remediation, Execution, Outcome) are consistent across DESIGN.md component tokens, EXPERIENCE.md Component Patterns, State Patterns, Stage Content table, and Key Flows.
- **Assumption tags:** EXPERIENCE.md State Patterns line 79 carries an inline `[ASSUMPTION]` tag for alert storm ceiling, matching PRD convention.
