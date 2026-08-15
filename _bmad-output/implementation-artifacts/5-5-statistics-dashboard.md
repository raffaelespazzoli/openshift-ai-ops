# Story 5.5: Statistics Dashboard

Status: done

## Story

As an ops team lead,
I want to see operational metrics and trends at a glance,
so that I can report on the tool's effectiveness and identify areas for improvement.

## Acceptance Criteria

1. **Given** the user navigates to the Statistics view **When** the page loads with data **Then** five PatternFly `Card` (compact) tiles render across the top row per UX-DR14: total incidents handled, auto-resolved percentage, success/failure ratio, mean time to resolution (MTTR), and fast-path hit rate **And** each card shows the current value and a trend indicator (up/down/flat compared to the previous period).

2. **Given** the Statistics view with data **When** the charts render **Then** PatternFly Charts display: alerts over time, diagnoses over time, and resolutions over time as line charts; MTTR as a separate area chart per UX-DR15.

3. **Given** the Statistics view **When** the user selects a time range **Then** a time-range selector offers day, week, and month options per UX-DR15 **And** all cards and charts update to reflect the selected range.

4. **Given** the Statistics view data **When** it is displayed **Then** the data is read-only — no approval or configuration actions are available from this view.

5. **Given** the Statistics view on a fresh deployment with no data **When** the page loads **Then** cards show "—" for values and charts display "No data for this time range." per UX-DR20.

6. **Given** the Statistics view is loading **When** the API calls are in flight **Then** cards display PatternFly `Skeleton` and charts show the PatternFly chart skeleton pattern per UX-DR17.

7. **Given** the backend REST API **When** the statistics endpoints are called **Then** they return aggregated data for the summary cards and time-series chart data filterable by the requested time range **And** responses follow the standard `{data, meta}` envelope.

## Tasks / Subtasks

- [ ] Task 1: Implement backend statistics API endpoints (AC: #7)
  - [ ] 1.1 Create `backend/src/db/statistics.py` — SQL aggregation queries for summary metrics and time-series data
  - [ ] 1.2 Create `backend/src/api/statistics.py` — REST endpoints `GET /api/v1/statistics/summary` and `GET /api/v1/statistics/timeseries`
  - [ ] 1.3 Register statistics router in `backend/src/api/app.py`
  - [ ] 1.4 Write unit tests in `backend/tests/api/test_statistics.py`

- [ ] Task 2: Create Statistics page layout and time-range selector (AC: #3, #4)
  - [ ] 2.1 Create `frontend/src/features/statistics/components/time-range-selector.tsx` — PatternFly ToggleGroup with day/week/month options
  - [ ] 2.2 Create `frontend/src/features/statistics/hooks/use-statistics.ts` — TanStack Query hook calling the statistics API
  - [ ] 2.3 Update `frontend/src/features/statistics/index.tsx` — replace EmptyState placeholder with full Statistics view layout
  - [ ] 2.4 Persist selected time range in URL query params (`?range=day|week|month`)

- [ ] Task 3: Implement summary cards row (AC: #1, #5, #6)
  - [ ] 3.1 Create `frontend/src/features/statistics/components/summary-cards.tsx` — five PatternFly Card (compact) tiles in a grid
  - [ ] 3.2 Implement trend indicators (up/down/flat arrow icons with semantic colors)
  - [ ] 3.3 Handle empty state (show "—" for values) and loading state (Skeleton)

- [ ] Task 4: Implement time-series charts (AC: #2, #5, #6)
  - [ ] 4.1 Create `frontend/src/features/statistics/components/activity-chart.tsx` — multi-line chart (alerts, diagnoses, resolutions over time)
  - [ ] 4.2 Create `frontend/src/features/statistics/components/mttr-chart.tsx` — area chart for MTTR
  - [ ] 4.3 Handle empty state ("No data for this time range." EmptyState) and loading state (chart Skeleton)
  - [ ] 4.4 Add accessible `aria-label` text summaries to each chart per UX-DR19

- [ ] Task 5: Install PatternFly Charts dependency
  - [ ] 5.1 Add `@patternfly/react-charts` and `victory` to `frontend/package.json`

- [ ] Task 6: Testing (AC: all)
  - [ ] 6.1 Write frontend tests: `summary-cards.test.tsx`, `activity-chart.test.tsx`, `mttr-chart.test.tsx`, `time-range-selector.test.tsx`
  - [ ] 6.2 Add MSW handlers for `/api/v1/statistics/summary` and `/api/v1/statistics/timeseries` in `frontend/src/mocks/handlers.ts`
  - [ ] 6.3 Include `jest-axe` assertion in every component test
  - [ ] 6.4 Backend: pytest tests for SQL aggregation logic and API endpoint responses

## Dev Notes

### Technical Stack (Dependencies for This Story)

| Package | Version | Purpose |
|---------|---------|---------|
| @patternfly/react-charts | 8.x (latest PF6-compatible) | Chart components (line, area) |
| victory | 37.x+ | Peer dependency for PF charts (Victory library) |

All other dependencies already installed in Story 5.1 (`@patternfly/react-core`, `@patternfly/react-icons`, `@tanstack/react-query`, `react-router-dom`, `vitest`, `@testing-library/react`, `msw`, `jest-axe`).

### Backend API Design

Two new endpoints under `/api/v1/statistics/`:

**`GET /api/v1/statistics/summary?range=day|week|month`**

Returns aggregated metrics for the summary cards.

```json
{
  "data": {
    "total_incidents": 142,
    "auto_resolved_pct": 67.5,
    "success_failure_ratio": "4.2:1",
    "mttr_seconds": 312,
    "fast_path_hit_rate_pct": 23.8,
    "trends": {
      "total_incidents": "up",
      "auto_resolved_pct": "flat",
      "success_failure_ratio": "up",
      "mttr_seconds": "down",
      "fast_path_hit_rate_pct": "up"
    }
  },
  "meta": { "timestamp": "...", "request_id": "..." }
}
```

Trend calculation: compare current period vs. previous period of the same length. "up" = increase >5%, "down" = decrease >5%, "flat" = within ±5%.

**`GET /api/v1/statistics/timeseries?range=day|week|month`**

Returns bucketed time-series data for charts.

```json
{
  "data": {
    "buckets": ["2026-08-14T00:00:00Z", "2026-08-14T01:00:00Z", ...],
    "alerts": [5, 3, 8, ...],
    "diagnoses": [4, 3, 7, ...],
    "resolutions": [3, 2, 6, ...],
    "mttr_seconds": [180, 240, 300, ...]
  },
  "meta": { "timestamp": "...", "request_id": "..." }
}
```

Bucket granularity: day=hourly (24 buckets), week=daily (7 buckets), month=daily (30 buckets).

### SQL Aggregation Logic (`backend/src/db/statistics.py`)

```python
async def get_summary_stats(conn, from_time, to_time, prev_from_time, prev_to_time):
    """Aggregate incident counts and metrics for summary cards."""

async def get_timeseries_stats(conn, from_time, to_time, bucket_interval):
    """Bucket incidents by time interval for chart data."""
```

Key queries against existing tables:
- `incidents` table: COUNT by state, time ranges, fast_path flag
- Resolution time: `updated_at - created_at` WHERE `state = 'resolved'`
- Auto-resolved: incidents that reached `resolved` without passing through `awaiting_approval`
- Fast-path hit rate: `COUNT(fast_path = TRUE) / COUNT(*)`

The `auto_resolved` calculation requires checking whether an incident ever transitioned through `awaiting_approval`. Since we don't persist transition history in a dedicated table, use the `approval_records` table presence — if no approval record exists for a resolved incident, it was auto-resolved (or fast-path resolved). This is the correct approach given the existing schema.

### PatternFly Charts Usage

Import from the Victory sub-package:

```typescript
import {
  Chart,
  ChartArea,
  ChartAxis,
  ChartGroup,
  ChartLine,
  ChartLegend,
  ChartVoronoiContainer,
  ChartThemeColor,
} from '@patternfly/react-charts/victory';
```

Key patterns:
- Apply `ChartThemeColor.multiOrdered` theme for multi-line charts
- Use `ChartVoronoiContainer` as the `containerComponent` for interactive tooltips
- Use `ChartGroup` to wrap multiple `ChartLine` components
- Use `monotoneX` interpolation for smooth line curves
- Chart sizing: use responsive width via `getResizeObserver` from `@patternfly/react-core`
- MTTR area chart: single `ChartArea` with `interpolation="monotoneX"`

### PatternFly Card Layout for Summary Tiles

Use PatternFly `Card` with `isCompact` prop. Five cards in a `Grid` with `GridItem` at `span={12}` on medium and `span={2}` (or equivalent) on xl+ for equal distribution.

```typescript
import { Card, CardBody, CardTitle, Grid, GridItem } from '@patternfly/react-core';
import { ArrowUpIcon, ArrowDownIcon, MinusIcon } from '@patternfly/react-icons';
```

Trend indicator mapping:
- "up" → `ArrowUpIcon` with `--pf-t--global--color--status--success--default` (for positive metrics like success ratio) or `--pf-t--global--color--status--danger--default` (for negative metrics like MTTR going up)
- "down" → `ArrowDownIcon` with appropriate semantic color
- "flat" → `MinusIcon` with `--pf-t--global--color--status--info--default`

Important: Trend arrow color meaning is context-dependent:
- Total incidents UP = neutral/info (not inherently good or bad)
- Auto-resolved % UP = success (good)
- Success ratio UP = success (good)
- MTTR DOWN = success (good), MTTR UP = danger (bad)
- Fast-path rate UP = success (good)

### Time-Range Selector

Use PatternFly `ToggleGroup` with `ToggleGroupItem` for day/week/month selection:

```typescript
import { ToggleGroup, ToggleGroupItem } from '@patternfly/react-core';
```

Persist in URL via `useSearchParams` from react-router-dom. Default to "week" if no query param present.

### Loading States (UX-DR17)

Cards: Use `Skeleton` components sized to match the card content area (width ~80px for value, ~40px for trend icon).

Charts: Use a layout-matching Skeleton — a rectangular `Skeleton` matching the chart dimensions with `shape="square"` or appropriate height.

### Empty States (UX-DR20)

Cards: Display "—" as the value text. No trend indicator shown.

Charts: Render PatternFly `EmptyState` centered in the chart area with text "No data for this time range." No action button (read-only view).

### File Structure

```
frontend/src/features/statistics/
  index.tsx                          # UPDATE — replace placeholder with full page
  components/
    summary-cards.tsx                 # NEW — five metric cards
    summary-cards.test.tsx            # NEW
    time-range-selector.tsx           # NEW — day/week/month toggle
    time-range-selector.test.tsx      # NEW
    activity-chart.tsx               # NEW — multi-line chart (alerts/diagnoses/resolutions)
    activity-chart.test.tsx          # NEW
    mttr-chart.tsx                   # NEW — area chart for MTTR
    mttr-chart.test.tsx             # NEW
  hooks/
    use-statistics.ts                # NEW — TanStack Query hooks

backend/src/
  api/statistics.py                  # NEW — REST endpoints
  db/statistics.py                   # NEW — SQL aggregation queries

backend/tests/
  api/test_statistics.py             # NEW — endpoint tests
```

### Architecture Compliance

- **FA-1 (Standalone-first):** Statistics data fetched via REST provider. DataProvider interface already supports this — just add query hooks.
- **FA-2 (TanStack Query):** All statistics data via `useQuery`. Query keys: `['statistics', 'summary', range]` and `['statistics', 'timeseries', range]`. `staleTime: 60000` (1 min — stats are not urgently real-time).
- **FA-4 (Code splitting):** Statistics feature is already lazily loaded from Story 5.1. New components are within the feature module.
- **AD-10 (API envelope):** Both endpoints return `{data, meta}` envelope.
- **AD-12 (Auth):** Endpoints require bearer token via `get_current_user` dependency.
- **AD-14 (Monorepo layout):** Frontend in `frontend/src/features/statistics/`, backend API in `backend/src/api/`, DB in `backend/src/db/`.

### Testing Requirements

**Frontend:**
- Every test file includes `expect(await axe(container)).toHaveNoViolations()`
- MSW handlers for both statistics endpoints (success + error + empty responses)
- Test loading state (Skeleton rendered while `isPending`)
- Test empty state (cards show "—", chart shows empty message)
- Test populated state (cards show numeric values, charts render SVG elements)
- Test time-range selector updates URL and triggers refetch
- Test accessible chart aria-labels
- No snapshot tests

**Backend:**
- pytest with `@pytest.mark.api` marker
- Test response envelope format
- Test `range` query param validation (reject invalid values)
- Test SQL aggregation with known test data (use `postgres_container` fixture from conftest)
- Test empty database returns zeroed stats

### Previous Story Intelligence

Story 5.1 established:
- Feature-based directory structure under `frontend/src/features/statistics/` (currently has `index.tsx` as placeholder `EmptyState`)
- TanStack Query setup with `QueryClientProvider` wrapping the app
- DataProvider interface in `frontend/src/providers/`
- MSW setup in `frontend/src/mocks/`
- PatternFly CSS imports and dark-mode default
- Vitest as test runner
- React Router with lazy-loaded routes
- API envelope types in `frontend/src/models/api.ts`

This story replaces the placeholder `EmptyState` in `frontend/src/features/statistics/index.tsx` with the full dashboard implementation.

### Anti-Patterns / DO NOT

- **DO NOT** use any charting library other than `@patternfly/react-charts` (Victory-based)
- **DO NOT** use hex colors or rgb() — all colors via PatternFly tokens
- **DO NOT** create custom wrapper components — use PF `Card`, `Chart*`, `Grid` directly
- **DO NOT** add any write/mutation actions to this view (read-only per AC #4)
- **DO NOT** implement SSE/real-time auto-refresh for statistics (not required — manual refresh via time-range change or page reload)
- **DO NOT** use snapshot tests
- **DO NOT** mock `fetch` directly — use MSW
- **DO NOT** add pagination to charts — render all buckets for the selected range
- **DO NOT** use `moment.js` or heavy date libraries — use `Intl.DateTimeFormat` for axis labels
- **DO NOT** use custom media queries — PatternFly grid breakpoints only
- **DO NOT** add animations or pulsing — clinical calm per UX-DR20

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.5] — acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR14] — summary cards spec
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR15] — charts and time-range spec
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR17] — loading state (Skeleton)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR19] — chart accessibility (aria-label)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR20] — empty state (dashes, "no data")
- [Source: _bmad-output/project-context.md#React + PatternFly (Frontend)] — PF rules
- [Source: _bmad-output/project-context.md#Frontend (TypeScript) Testing] — test standards
- [Source: _bmad-output/project-context.md#Frontend Architecture Decisions] — FA-1 through FA-4
- [Source: _bmad-output/project-context.md#Frontend Anti-Patterns] — don't-miss rules
- [Source: _bmad-output/implementation-artifacts/5-1-frontend-scaffolding-and-app-shell.md] — established patterns
- [Source: backend/src/api/incidents.py] — API endpoint pattern (auth, envelope, pagination)
- [Source: backend/src/db/incidents.py] — DB query patterns (asyncpg, parameterized queries)
- [Source: backend/src/models/api.py] — ApiResponse, ApiMeta, ApiError models
- [Source: charts/openshift-ai-ops/values.yaml] — no frontend changes needed for this story

## Code Review Record

### Review Round 1 — 2026-08-15
**Review model:** GPT-5.4
**Fix model:** claude-4.6-opus

#### Findings
- [x] [Review][Patch] Missing sealed_at bucketing regression coverage [`backend/tests/api/test_statistics.py`] — This round changes `get_timeseries_stats()` to bucket diagnosis counts from `immutable_diagnoses.sealed_at`, but the statistics tests still cover only API envelopes and summary aggregation. There is no targeted test that seeds diagnoses into different time buckets and proves diagnoses are counted by `sealed_at` instead of mutable incident timestamps, so this exact bug can regress silently in a future refactor. **Fixed**: Added `TestTimeseriesDiagnosisBucketing` class with two targeted regression tests verifying SQL references `immutable_diagnoses`/`sealed_at` and that diagnosis counts are independent of alert counts.

### Review Round 5 (FINAL) — 2026-08-15
**Review model:** claude-4.6-opus
**Fix model:** N/A — no fixes required

#### Findings
No new findings. All three review layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor) passed clean. Prior Round 1 finding verified fixed via commit `ed8beb4`.

## Dev Agent Record

### Agent Model Used

_(To be filled during development)_

### Debug Log References

### Completion Notes List

### File List
