# Story 5.2: Incidents List View

Status: done

## Story

As an SRE,
I want to see all active incidents organized by root-cause groups with filtering,
so that I can quickly scan the current state of the cluster and focus on what needs my attention.

## Acceptance Criteria

1. **Given** the Incidents view loads with active incidents **When** the DataList renders **Then** incidents are grouped by Root-Cause Event as expandable rows per UX-DR7 **And** each RCE group header shows: RCE label, correlated alert count badge, highest severity Label (PatternFly `Label` with `danger`/`warning`/`info` variant), and time since first alert **And** groups are collapsed by default, sorted by highest severity first.

2. **Given** an RCE group header **When** the user clicks it **Then** it expands to reveal individual alert rows within the group (no page navigation).

3. **Given** an individual alert row within an expanded RCE group **When** the user clicks it **Then** the application navigates to the full-page Incident Detail view.

4. **Given** a fast-path incident exists in the list **When** it is rendered **Then** a PatternFly `Label` (info, compact) with "Fast-Path" text is displayed on the row per UX-DR4.

5. **Given** the Incidents toolbar **When** it renders **Then** it includes a Firing/Resolved `ToggleGroup` (Firing selected by default) per UX-DR8 **And** selecting "Resolved" reveals a time-range dropdown (1h, 6h, 24h, 7d).

6. **Given** the Incidents toolbar **When** it renders **Then** it includes a severity `Select` (checkbox variant) for multi-select filtering (critical, warning, info — all selected by default) per UX-DR9.

7. **Given** the Firing/Resolved toggle or severity filter is changed **When** the filter state updates **Then** the selection persists in URL query parameters per UX-DR22 **And** navigating back from the detail view restores the filter state.

8. **Given** no alerts are currently firing **When** the Incidents view loads in Firing mode **Then** a PatternFly `EmptyState` is displayed with check-circle success icon and text "No active alerts." — no call-to-action per UX-DR16.

9. **Given** the Incidents view is loading data **When** the API call is in flight **Then** PatternFly `Skeleton` rows (6–8) matching the DataList layout shape are displayed per UX-DR17.

10. **Given** the API returns an error **When** the Incidents view handles it **Then** a PatternFly `EmptyState` with danger icon displays "Unable to reach the API." with a Retry button per UX-DR20.

## Tasks / Subtasks

- [ ] Task 1: Create incident TypeScript models (AC: #1, #4)
  - [ ] 1.1 Define `Incident` type in `frontend/src/models/incident.ts` matching backend response shape (`id`, `state`, `severity`, `created_at`, `updated_at`, `fast_path`, alert count, RCE label)
  - [ ] 1.2 Define `Alert` type matching backend alert response (`id`, `fingerprint`, `labels`, `annotations`, `status`, `fired_at`, `resolved_at`)
  - [ ] 1.3 Define `IncidentListItem` type representing the grouped/list API response shape
  - [ ] 1.4 Define `IncidentFilters` type for URL-persisted filter state (`mode: 'firing' | 'resolved'`, `severities: string[]`, `timeRange?: string`)

- [ ] Task 2: Implement incidents API hook with TanStack Query (AC: #1, #5, #6, #7)
  - [ ] 2.1 Create `frontend/src/features/incidents/hooks/use-incidents.ts` with `useIncidents(filters)` hook
  - [ ] 2.2 Hook calls `GET /api/v1/incidents` with query params mapped from filter state (`status=active` for firing, `status=resolved` for resolved + time range)
  - [ ] 2.3 Query key includes all filter dimensions: `['incidents', mode, severities, timeRange]`
  - [ ] 2.4 Configure `staleTime: 30000` (30s) per FA-2 convention
  - [ ] 2.5 `queryFn` throws on non-OK responses per TanStack Query v5 pattern

- [ ] Task 3: Implement URL-persisted filter state (AC: #7)
  - [ ] 3.1 Create `frontend/src/features/incidents/hooks/use-incident-filters.ts`
  - [ ] 3.2 Read initial state from `URLSearchParams` on mount: `mode` param (default "firing"), `severity` param (comma-separated, default all), `timeRange` param (default "24h")
  - [ ] 3.3 Write state changes back to URL via `window.history.replaceState` (no navigation)
  - [ ] 3.4 Export typed `IncidentFilters` object and setter functions

- [ ] Task 4: Implement incidents toolbar with filters (AC: #5, #6)
  - [ ] 4.1 Create `frontend/src/features/incidents/components/incidents-toolbar.tsx`
  - [ ] 4.2 Render PatternFly `Toolbar` with `ToolbarContent` and `ToolbarItem` groups
  - [ ] 4.3 Add `ToggleGroup` with two items: "Firing" (default selected), "Resolved"
  - [ ] 4.4 When "Resolved" is selected, show time-range `Select` (single) with options: 1h, 6h, 24h, 7d
  - [ ] 4.5 Add severity `Select` (checkbox variant) with "Critical", "Warning", "Info" — all checked by default
  - [ ] 4.6 Wire filter changes to the `useIncidentFilters` hook (updates URL + triggers query refetch)

- [ ] Task 5: Implement DataList with expandable RCE groups (AC: #1, #2, #3, #4)
  - [ ] 5.1 Create `frontend/src/features/incidents/components/incidents-list.tsx`
  - [ ] 5.2 Use PatternFly `DataList` with `DataListItem` per RCE group (expandable)
  - [ ] 5.3 Render group header: RCE label text, alert count badge (`Badge`), severity `Label` (danger/warning/info variant matching highest severity), relative time since first alert
  - [ ] 5.4 Sort groups by severity: critical first, then warning, then info
  - [ ] 5.5 All groups collapsed by default — expand on click per AC #2
  - [ ] 5.6 Expanded group shows individual alert rows with alert name, fingerprint, and firing time
  - [ ] 5.7 Click on individual alert row navigates to `/incidents/{id}` via React Router
  - [ ] 5.8 For fast-path incidents, render `Label` with `color="blue"` (info variant), compact, text "Fast-Path"

- [ ] Task 6: Implement loading, empty, and error states (AC: #8, #9, #10)
  - [ ] 6.1 Create `frontend/src/features/incidents/components/incidents-skeleton.tsx` — 6–8 `Skeleton` rows matching DataList shape
  - [ ] 6.2 Render skeleton when `isPending` is true (TanStack Query v5)
  - [ ] 6.3 Render `EmptyState` with `CheckCircleIcon` (success) and "No active alerts." when data is empty in Firing mode
  - [ ] 6.4 Render `EmptyState` with `ExclamationCircleIcon` (danger) and "Unable to reach the API." + Retry button on error
  - [ ] 6.5 Retry button calls `queryClient.invalidateQueries({ queryKey: ['incidents'] })`

- [ ] Task 7: Wire up the Incidents route entry point (AC: all)
  - [ ] 7.1 Update `frontend/src/features/incidents/index.tsx` to compose: toolbar + list/skeleton/empty/error
  - [ ] 7.2 Ensure the route preserves filter state on back-navigation from detail view

- [ ] Task 8: Testing (AC: all)
  - [ ] 8.1 Add MSW handler for `GET /api/v1/incidents` in `frontend/src/mocks/handlers.ts` returning mock incident list
  - [ ] 8.2 Write test for incidents list: verifies DataList renders RCE groups, severity labels, alert count
  - [ ] 8.3 Write test for expand/collapse: click group header expands, shows alert rows
  - [ ] 8.4 Write test for filter toolbar: toggle Firing/Resolved, severity select changes query params
  - [ ] 8.5 Write test for URL persistence: initial load reads params, changes write params
  - [ ] 8.6 Write test for empty state: no data shows "No active alerts."
  - [ ] 8.7 Write test for error state: API error shows danger empty state + retry button
  - [ ] 8.8 Write test for loading state: pending shows skeleton rows
  - [ ] 8.9 Write test for fast-path badge: fast-path incident shows "Fast-Path" label
  - [ ] 8.10 Include `jest-axe` assertion in every test: `expect(await axe(container)).toHaveNoViolations()`

### Review Findings

- [x] [Review][Decision] Safety cap truncates the "full scroll" incidents list — `backend/src/db/incidents.py` now hard-limits `GET /api/v1/incidents` to 1000 rows, while `backend/src/api/incidents.py` reports `meta.total = len(serialized)`. If a cluster has more than 1000 matching incidents, the frontend receives a truncated list with no signal that results were dropped, which conflicts with the story and UX requirement that v1 renders the full incidents list with scroll instead of pagination. **Fixed**: User decided to re-introduce pagination. Backend now has proper LIMIT/OFFSET with COUNT query for total. Frontend has PF Pagination component in toolbar.
- [x] [Review][Patch] Story 5.2 UI is still a placeholder [`frontend/src/features/incidents/index.tsx:6`] — The Incidents route still renders "Incident list view coming soon.", and there are no Story 5.2 `components/` or `hooks/` files under `frontend/src/features/incidents/`, so the toolbar, DataList, grouping, loading, empty, error, and URL-persisted filter behaviors in AC 1-10 are not implemented in this worktree. **Fixed**: Full incidents list view implemented — toolbar with filters, DataList with expandable rows, skeleton/empty/error states, URL-persisted filters, pagination.
- [x] [Review][Patch] Frontend incident model still mismatches the backend list contract [`frontend/src/models/incident.ts:25`] — The exported `Incident` type still expects `title`, `status`, `root_cause_code`, and `alerts`, while the backend list endpoint returns `id`, `state`, `severity`, `created_at`, `updated_at`, and `fast_path`. Adding `planning` fixes one enum value, but the API contract is still not aligned. **Fixed**: Frontend `IncidentListItem` type now matches backend list response shape. `IncidentState` type includes `planning`.

## Dev Notes

### Technical Stack (Exact Versions)

Same as Story 5.1 — no new dependencies introduced. This story uses packages already installed:

| Package | Version | Usage in This Story |
|---------|---------|---------------------|
| @patternfly/react-core | 6.6.x | DataList, Toolbar, ToggleGroup, Select, Label, Badge, EmptyState, Skeleton |
| @patternfly/react-icons | 6.6.x | CheckCircleIcon, ExclamationCircleIcon |
| @tanstack/react-query | 5.x | useQuery for incidents list |
| react-router-dom | 7.x | useNavigate, useSearchParams |
| msw | 2.x | Mock incident API for tests |

### Architecture Decisions to Follow

- **FA-1 (Standalone-first, Console-ready):** All API calls go through the `DataProvider` / REST provider abstraction established in 5.1. Do NOT call `fetch` directly from components.
- **FA-2 (TanStack Query for server state):** `useQuery({ queryKey: ['incidents', ...filters], queryFn })`. Use `isPending` for first-load state. Never `useState` + `useEffect` for API data.
- **FA-3 (SSE for real-time):** SSE subscription is NOT this story — Story 5.4 wires up live updates. This story uses polling via TanStack Query `staleTime` only.
- **FA-4 (Feature-based code splitting):** The `incidents/index.tsx` is already lazy-loaded from Story 5.1's routing setup.

### PatternFly 6 Component Usage (Incidents List View)

```
PageSection                    — content wrapper (from App Shell)
  Toolbar                      — filter controls container
    ToolbarContent             — toolbar content wrapper
      ToolbarItem              — each filter element
        ToggleGroup            — Firing/Resolved toggle
          ToggleGroupItem      — "Firing" | "Resolved"
        Select (checkbox)      — Severity multi-select filter
        Select (single)        — Time range (visible only in Resolved mode)
  DataList                     — incident list
    DataListItem (expandable)  — one per RCE group
      DataListItemRow          — group header row
        DataListItemCells      — cells container
          DataListCell         — RCE label, Badge (alert count), Label (severity), time
      DataListContent          — expanded content (alert rows)
        DataList (nested)      — individual alerts within the group
          DataListItem         — one per alert (clickable → detail)
  EmptyState                   — no data / error states
  Skeleton                     — loading state
```

### Backend API Contract

**Endpoint:** `GET /api/v1/incidents`

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `status` | `string[]` | Filter by state. Use `active` for all non-terminal (firing). Use `resolved`, `failed` for resolved. |
| `severity` | `string[]` | Filter by severity: `critical`, `warning`, `info` |
| `from_time` | `ISO 8601` | Start of time range (Resolved mode) |
| `to_time` | `ISO 8601` | End of time range (Resolved mode) |
| `page` | `int` | Page number (default 1) |
| `page_size` | `int` | Items per page (default 50, max 200) |

**Response shape:**
```typescript
interface IncidentListResponse {
  data: Array<{
    id: string;         // UUID
    state: string;      // IncidentState enum value
    severity: string;   // "critical" | "warning" | "info"
    created_at: string; // ISO 8601
    updated_at: string; // ISO 8601
    fast_path: boolean;
  }>;
  meta: {
    timestamp: string;
    request_id: string;
    page: number;
    page_size: number;
    total: number;
  };
}
```

**Important:** The current backend returns a flat list of incidents — NOT pre-grouped by RCE. The frontend is responsible for grouping incidents into RCE groups. Since the current data model does not have an explicit `rce_group_id` field, grouping is determined by correlation: incidents created within the same correlation window share the same logical RCE group. For v1, treat each incident as its own group (one incident = one RCE group header with its alerts expandable). The grouping logic will be refined when the backend adds explicit RCE group fields.

**Firing vs Resolved mapping:**
- "Firing" → `status=active` (maps to all non-terminal states: received, correlating, queued, diagnosing, diagnosed, planning, awaiting_approval, executing, observing)
- "Resolved" → `status=resolved&status=failed` + `from_time` / `to_time` based on time-range selection

### URL Query Parameter Schema

```
?mode=firing|resolved
&severity=critical,warning,info    (comma-separated)
&timeRange=1h|6h|24h|7d           (only when mode=resolved)
```

Use `URLSearchParams` for read/write. Use `window.history.replaceState` for updates (no full navigation). The `useSearchParams` hook from React Router can also be used.

### Date Formatting

- Time since first alert: use `Intl.RelativeTimeFormat` for < 24h (e.g., "3 minutes ago", "2 hours ago"). For > 24h, display absolute ISO 8601 date. No `moment.js`.
- Utility function already planned in `frontend/src/utils/date.ts` from Story 5.1.

### File Structure (This Story)

```
frontend/src/
  features/
    incidents/
      components/
        incidents-toolbar.tsx       # NEW — filter toolbar
        incidents-toolbar.test.tsx  # NEW — toolbar tests
        incidents-list.tsx          # NEW — DataList with RCE groups
        incidents-list.test.tsx     # NEW — list tests
        incidents-skeleton.tsx      # NEW — loading skeleton
      hooks/
        use-incidents.ts            # NEW — TanStack Query hook for incident list
        use-incidents.test.ts       # NEW — hook tests
        use-incident-filters.ts    # NEW — URL-persisted filter state
        use-incident-filters.test.ts # NEW — filter hook tests
      index.tsx                     # UPDATE — compose toolbar + list + states
      index.test.tsx                # NEW — integration test for full view
  models/
    incident.ts                     # UPDATE — add full Incident/Alert types (may be placeholder from 5.1)
  mocks/
    handlers.ts                     # UPDATE — add incidents list mock handler
```

### Story Intelligence Chain

**Predecessor: Story 5.1 (Frontend Scaffolding & App Shell)**

What 5.1 accomplished:
- React 19 + TypeScript + Vite project scaffolded in `frontend/src/`
- PatternFly 6 installed and configured (dark mode default)
- App Shell with Masthead + PageSidebar + Nav (Incidents, Statistics)
- React Router with lazy-loaded routes
- DataProvider abstraction + REST provider with API envelope handling
- TanStack Query setup with QueryClientProvider
- OpenShift OAuth stub
- MSW test infrastructure with centralized handlers
- Helm chart frontend deployment (nginx + Dockerfile)
- Error boundary on each route

What 5.1 deferred to this story:
- Actual incidents list view (was placeholder `EmptyState`)
- URL filter state persistence
- Real data fetching for incidents

What patterns 5.1 established:
- Kebab-case filenames throughout
- Feature-based directory structure (`features/incidents/`, `features/statistics/`)
- PatternFly components used directly (no wrappers)
- TanStack Query object syntax: `useQuery({ queryKey, queryFn })`
- MSW handlers in `mocks/handlers.ts`
- jest-axe on every test
- Error boundary wrapping each route component
- `DataProvider` interface as the migration seam

What this story inherits:
- The Incidents route entry point (`features/incidents/index.tsx`) already exists as a placeholder — this story replaces it with the real list view
- The React Router setup already handles `/incidents` route
- The `models/` directory may have placeholder types from 5.1 — extend them
- `mocks/handlers.ts` already has a structure to add new handlers into

### Anti-Patterns / DO NOT

- **DO NOT** create custom wrapper components around PatternFly (no `<IncidentBadge>` wrapping `<Label>`)
- **DO NOT** use `useState` + `useEffect` for data fetching — use TanStack Query exclusively
- **DO NOT** implement SSE / real-time updates — that is Story 5.4's responsibility
- **DO NOT** implement the incident detail view — that is Story 5.3's responsibility
- **DO NOT** implement approval actions — that is Story 5.4's responsibility
- **DO NOT** implement the NotificationBadge on the nav item — that requires approval count (Story 5.4)
- **DO NOT** implement keyboard shortcuts (j/k navigation) — that is Story 5.6's responsibility
- **DO NOT** implement pagination UI — v1 renders all incidents; scroll only per UX state patterns
- **DO NOT** use hex colors or `rgb()` — all colors via PatternFly tokens
- **DO NOT** use `moment.js` or heavy date libraries — use `Intl.RelativeTimeFormat`
- **DO NOT** add animations or pulsing indicators — clinical calm per UX-DR20
- **DO NOT** use snapshot tests — forbidden per project rules
- **DO NOT** mock `fetch` directly in tests — use MSW at the network level
- **DO NOT** add custom media queries — use PatternFly grid breakpoints only
- **DO NOT** use `data-testid` unless no accessible query alternative exists — prefer `getByRole`, `getByLabelText`, `getByText`
- **DO NOT** add new npm dependencies — all needed packages are installed from Story 5.1
- **DO NOT** modify the App Shell, routing, or provider infrastructure — those are stable from 5.1

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5, Story 5.2] — acceptance criteria and user story
- [Source: _bmad-output/project-context.md#TypeScript (Frontend)] — coding conventions
- [Source: _bmad-output/project-context.md#React + PatternFly (Frontend)] — framework rules
- [Source: _bmad-output/project-context.md#Frontend (TypeScript) Testing] — test standards
- [Source: _bmad-output/project-context.md#Frontend Architecture Decisions] — FA-1 through FA-4
- [Source: _bmad-output/project-context.md#Frontend Anti-Patterns] — critical don't-miss rules
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-openshift-ai-ops-2026-08-02/DESIGN.md#Components] — DataList, Label, ToggleGroup, Select, EmptyState, Skeleton
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-openshift-ai-ops-2026-08-02/EXPERIENCE.md#Component Patterns] — Incident list behavioral rules
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-openshift-ai-ops-2026-08-02/EXPERIENCE.md#State Patterns] — loading, empty, error treatments
- [Source: backend/src/api/incidents.py] — backend endpoint with query params and response shape
- [Source: backend/src/models/incident.py] — Incident model (id, state, severity, created_at, updated_at)
- [Source: backend/src/models/state_machine.py] — IncidentState enum and terminal states
- [Source: backend/src/models/api.py] — ApiResponse, ApiMeta, ApiError envelope types
- [Source: backend/src/db/incidents.py#list_incidents] — SQL query shape (filtering, pagination, ordering)
- [Source: _bmad-output/implementation-artifacts/5-1-frontend-scaffolding-and-app-shell.md] — predecessor story patterns and decisions

## Code Review Record

### Review Round 3 — 2026-08-15
**Review model:** GPT-5.4
**Fix model:** Claude Opus 4.6

#### Findings
- [x] [Review][Decision] Safety cap truncates the "full scroll" incidents list — `backend/src/db/incidents.py` hard-limits the query to 1000 rows and `backend/src/api/incidents.py` reports `meta.total = len(serialized)`, so the frontend cannot detect truncation once matches exceed 1000. **Fixed**: Pagination re-introduced at both API and UI levels with COUNT query for accurate total.
- [x] [Review][Patch] Story 5.2 UI is still a placeholder [`frontend/src/features/incidents/index.tsx:6`] — The current worktree still serves a placeholder `EmptyState`, and the Story 5.2 incidents list components/hooks are absent. **Fixed**: Full UI implemented — toolbar, DataList, skeleton, empty/error states.
- [x] [Review][Patch] Frontend incident model still mismatches the backend list contract [`frontend/src/models/incident.ts:25`] — The frontend type still models `title`/`status`/`root_cause_code`/`alerts` instead of the backend list payload fields, so the API contract is not yet aligned. **Fixed**: `IncidentListItem` type now matches backend response shape.

### Review Round 4 — 2026-08-15
**Review model:** Claude Opus 4.6
**Fix model:** Claude Opus 4.6

#### Findings
- [x] [Review][Patch] Frontend→backend query param encoding mismatch for multi-value filters [`frontend/src/features/incidents/hooks/use-incidents.ts:21`] — `buildParams` sends `status` and `severity` as comma-joined single values (e.g., `status=received,correlating,...`), but the FastAPI endpoint declares `status: list[str] | None = Query(None)` which expects repeated params (`?status=received&status=correlating`). The `restProvider.get()` uses `url.searchParams.set()` which only supports single values per key, and the `DataProvider` interface types params as `Record<string, string>`. The comma-joined value is received as a single-element list `["received,correlating,..."]` which matches no incident state — filtering is completely broken against the real backend. MSW mock ignores filter params, hiding this from tests. **Fixed**: `DataProvider.get()` signature widened to `Record<string, string | string[]>`, `restProvider.get()` now handles arrays via `append()`, and `buildParams()` returns arrays for multi-value params.
- [x] [Review][Patch] Backend test contradicts backend API pagination implementation [`backend/tests/api/test_incidents.py:89`] — `test_no_pagination_params_accepted` asserts `meta.get("page") is None` and `meta.get("page_size") is None`, but the API endpoint explicitly passes `page=page, page_size=page_size` to `ApiMeta`. This test will fail against the real API — it is a leftover from the iter-2 "remove pagination" fix, not updated after pagination was restored. **Fixed**: Stale test replaced with `test_default_pagination_params` (verifies page=1, page_size=50) and `test_custom_pagination_params` (verifies custom values).
- [x] [Review][Patch] Fast-path Label deviates from spec in color, compactness, and text [`frontend/src/features/incidents/components/incidents-list.tsx:90`] — AC #4 and Task 5.8 specify `color="blue"` (info variant), `isCompact`, and text "Fast-Path". The code uses `color="green"`, no `isCompact` prop, and text "Fast path" (lowercase 'p', no hyphen). **Fixed**: Label now uses `color="blue"` `isCompact` with text "Fast-Path".
- [x] [Review][Patch] Incidents not sorted by highest severity first [`backend/src/db/incidents.py:176`] — AC #1 requires "sorted by highest severity first." The backend query sorts only by `created_at DESC`. With pagination, severity sort must happen server-side via a `CASE` expression in `ORDER BY`. **Fixed**: SQL ORDER BY now uses `CASE i.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 WHEN 'info' THEN 3 ELSE 4 END, i.created_at DESC`.
- [x] [Review][Patch] Raw HTML button with inline styles instead of PatternFly Button [`frontend/src/features/incidents/components/incidents-list.tsx:71`] — A raw `<button>` with 7 inline style properties is used for the navigation link. Project rule: "use PF components exclusively." Should use PF `Button variant="link" isInline`. **Fixed**: Replaced with `<Button variant="link" isInline>`.
- [x] [Review][Patch] Resolved mode defaults timeRange to undefined instead of '24h' [`frontend/src/features/incidents/hooks/use-incident-filters.ts:21`] — Task 3.2 specifies default '24h' for timeRange, but `parseFilters` defaults to `undefined` when no URL param exists. All resolved incidents are fetched with no time bound when switching to Resolved mode. **Fixed**: Default timeRange is now `'24h'`.
- [x] [Review][Patch] Unused Title import [`frontend/src/features/incidents/index.tsx:7`] — `Title` is imported from `@patternfly/react-core` but never used. **Fixed**: Import removed.
- [x] [Review][Patch] Tests query by PF CSS class and id patterns instead of accessible queries [`frontend/src/features/incidents/components/incidents-skeleton.test.tsx:14`] — `incidents-skeleton.test.tsx` uses `querySelectorAll('[id^="skeleton-"]')` and `incidents-toolbar.test.tsx` uses `querySelector('.pf-v6-c-pagination')`. Project rule: test by role, label, or text — never by CSS class unless no accessible alternative exists. **Fixed**: Skeleton test uses `getAllByRole('listitem')`, toolbar test uses `getAllByText(/120/)`.

### Review Round 5 — 2026-08-15
**Review model:** Claude Opus 4.6
**Fix model:** N/A — clean review, no fixes required

#### Findings
No findings. All three review layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor) returned clean results. All 8 iter-4 findings verified as correctly fixed in the current code. All 10 acceptance criteria satisfied. API contract aligned between frontend and backend. PatternFly 6 components used correctly throughout. Test coverage comprehensive with jest-axe accessibility checks on every test file.

## Dev Agent Record

### Agent Model Used

_(To be filled during development)_

### Debug Log References

### Completion Notes List

### File List
