# Story 5.4: Approval Workflow & Real-Time Updates

Status: ready-for-dev

## Story

As an on-call SRE,
I want to approve or reject remediations directly in the UI with real-time pipeline progress,
so that I can act on recommendations immediately without refreshing the page or polling for updates.

## Acceptance Criteria

1. **Given** an incident is in `awaiting_approval` state **When** the detail view loads **Then** the Remediation stage auto-expands with Approve (PatternFly `Button`, primary) and Reject (PatternFly `Button`, danger) buttons as the first element in the panel per UX-DR12 **And** these are single-click actions with no confirmation modal for standard blast radius.

2. **Given** the user clicks Approve **When** the API call succeeds **Then** the pipeline visualization updates in real time: Remediation transitions to `completed`, Execution transitions to `active` **And** the navigation approval badge count decrements.

3. **Given** the user clicks Reject **When** the API call succeeds **Then** the incident transitions to `failed` state and the pipeline reflects it.

4. **Given** incidents are awaiting approval **When** the sidebar navigation renders **Then** the "Incidents" nav item displays a PatternFly `NotificationBadge` with the count of items in `awaiting` state per UX-DR3 **And** the badge is hidden when the count is 0.

5. **Given** the user is viewing an incident detail page **When** any pipeline stage transitions **Then** the update arrives via SSE subscription per UX-DR21 **And** the pipeline visualization updates without page refresh.

6. **Given** a pipeline stage is in `active` state **When** the detail view is displayed **Then** it auto-refreshes every 5 seconds while any stage is active per UX-DR20.

7. **Given** the SSE connection drops **When** reconnection fails **Then** the frontend falls back to polling the REST API for updates per UX-DR21.

## Tasks / Subtasks

- [ ] Task 1: Approve/Reject buttons in Remediation panel (AC: #1, #2, #3)
  - [ ] 1.1 Modify `frontend/src/features/incidents/components/remediation-panel.tsx` — add Approve (primary) and Reject (danger) buttons at the top of the panel when `incident.state === 'awaiting_approval'`
  - [ ] 1.2 Create mutation hook `useApproveIncident(id)` calling `POST /api/v1/incidents/{id}/approve` via TanStack Query `useMutation`
  - [ ] 1.3 Create mutation hook `useRejectIncident(id)` calling `POST /api/v1/incidents/{id}/reject` with `{ reason }` body
  - [ ] 1.4 On Approve success: invalidate `['incidents', id]` and `['incidents-awaiting']` queries, optimistic UI transition (Remediation → completed, Execution → active)
  - [ ] 1.5 On Reject success: invalidate `['incidents', id]` and `['incidents-awaiting']` queries, optimistic UI (pipeline → failed state)
  - [ ] 1.6 Add loading state on button (spinner/disabled) while mutation is in-flight
  - [ ] 1.7 Display inline PatternFly `Alert` (danger) on mutation error with retry option
  - [ ] 1.8 Handle minimum review time: if API returns 409 with `review_time_remaining`, show countdown or disabled state with tooltip

- [ ] Task 2: Reject reason modal (AC: #3)
  - [ ] 2.1 When Reject is clicked, show PatternFly `Modal` with `TextArea` for rejection reason (required)
  - [ ] 2.2 Modal has "Reject" (danger) and "Cancel" buttons
  - [ ] 2.3 Validate reason is non-empty before submitting

- [ ] Task 3: NotificationBadge for awaiting-approval count (AC: #4)
  - [ ] 3.1 Create hook `useAwaitingApprovalCount()` calling `GET /api/v1/incidents/awaiting-approval` via TanStack Query
  - [ ] 3.2 Modify the sidebar Nav component (in `frontend/src/app/`) to display PatternFly `NotificationBadge` on the "Incidents" nav item
  - [ ] 3.3 Badge hidden when count is 0; shows numeric count otherwise
  - [ ] 3.4 Query auto-refetches on window focus and has 30s `staleTime`
  - [ ] 3.5 SSE events invalidate the `['incidents-awaiting']` query key (wired in Task 5)

- [ ] Task 4: SSE subscription hook (AC: #5, #6, #7)
  - [ ] 4.1 Create `frontend/src/hooks/use-sse.ts` — shared SSE subscription hook using `EventSource`
  - [ ] 4.2 Connect to `GET /api/v1/events/stream` with `Authorization` header (via polyfill or custom fetch-based SSE, since native `EventSource` doesn't support headers)
  - [ ] 4.3 Parse incoming events: match `event_name` and `incident_id`
  - [ ] 4.4 Implement reconnect with exponential backoff: initial 1s, max 30s, jitter (per project-context.md SSE rules)
  - [ ] 4.5 Support `Last-Event-ID` header on reconnection for replay from the event bus
  - [ ] 4.6 Close EventSource on component unmount (cleanup in useEffect return)
  - [ ] 4.7 Expose connection state: `connected`, `reconnecting`, `disconnected`

- [ ] Task 5: SSE integration with TanStack Query (AC: #5, #6)
  - [ ] 5.1 Create `frontend/src/hooks/use-incident-sse.ts` — wires SSE events to query invalidation
  - [ ] 5.2 On `incident.state_changed` or `incident.stage_changed` for the viewed incident: `queryClient.invalidateQueries({ queryKey: ['incidents', id] })`
  - [ ] 5.3 On `incident.approval_decision`: invalidate `['incidents-awaiting']` query
  - [ ] 5.4 On `incident.created` or `incident.resolved`: invalidate `['incidents']` list query
  - [ ] 5.5 Wire `useIncidentSSE` into the incident detail page component

- [ ] Task 6: Polling fallback on SSE disconnect (AC: #6, #7)
  - [ ] 6.1 In `useIncidentSSE`, detect when connection state is `disconnected`
  - [ ] 6.2 When disconnected, enable TanStack Query `refetchInterval: 5000` on the incident detail query
  - [ ] 6.3 When reconnected, disable polling (set `refetchInterval` back to `false`)
  - [ ] 6.4 Show subtle inline indicator (PatternFly `Label` or small text) when operating in polling fallback mode

- [ ] Task 7: Auto-refresh while stage is active (AC: #6)
  - [ ] 7.1 In incident detail page, detect if any pipeline stage state is `active`
  - [ ] 7.2 While active and SSE is connected: rely on SSE (no polling needed)
  - [ ] 7.3 While active and SSE is disconnected: 5s `refetchInterval` is already active from Task 6
  - [ ] 7.4 When incident reaches terminal state (`resolved`/`failed`): stop all auto-refresh

- [ ] Task 8: Tests (AC: all)
  - [ ] 8.1 Unit test: Approve/Reject buttons render only when `state === 'awaiting_approval'`
  - [ ] 8.2 Unit test: clicking Approve calls POST endpoint, updates pipeline stepper
  - [ ] 8.3 Unit test: clicking Reject opens modal, submitting calls POST with reason
  - [ ] 8.4 Unit test: NotificationBadge renders count; hidden when 0
  - [ ] 8.5 Unit test: SSE hook reconnects with backoff on connection drop
  - [ ] 8.6 Unit test: SSE event invalidates TanStack Query cache
  - [ ] 8.7 Unit test: polling fallback activates when SSE disconnects
  - [ ] 8.8 Unit test: minimum review time shows disabled state or countdown
  - [ ] 8.9 Every test includes `expect(await axe(container)).toHaveNoViolations()`
  - [ ] 8.10 MSW handlers for: `POST /api/v1/incidents/:id/approve`, `POST /api/v1/incidents/:id/reject`, `GET /api/v1/incidents/awaiting-approval`

## Dev Notes

### Technical Stack (Exact Versions — inherit from Story 5.1)

| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.x | UI framework |
| @patternfly/react-core | 6.6.x | Button, NotificationBadge, Modal, TextArea, Alert, Label |
| @patternfly/react-icons | 6.6.x | BellIcon (for badge) |
| @tanstack/react-query | 5.x | useQuery, useMutation, queryClient.invalidateQueries |
| react-router-dom | 7.x | Route context |
| vitest | latest | Test runner |
| @testing-library/react | latest | Component testing |
| jest-axe | latest | Accessibility assertions |
| msw | 2.x | Mock API and SSE responses |

### Story Intelligence Chain

**Story 5.3 (direct dependency):** Built the static incident detail view with pipeline ProgressStepper, stage content panels (including `remediation-panel.tsx`), and the `useIncidentDetail(id)` TanStack Query hook. Key patterns this story inherits:
- `expandedStage` state management for one-at-a-time accordion panels
- `getStageStates()` utility mapping incident state to per-stage visual states
- PatternFly ProgressStep variant mapping (success/info/warning/danger/default)
- The Remediation panel already renders steps, blast radius, rollback plan, dry-run badge — we ADD approve/reject buttons at the top
- MSW handler for `GET /api/v1/incidents/:id` with full incident detail mock data
- File structure in `frontend/src/features/incidents/components/`

**Story 5.1 (app shell):** Established the sidebar Nav, App shell layout, `QueryClient` setup, `providers/` interface, OAuth token injection, and the feature-based directory layout. The `NotificationBadge` goes into the existing Nav component created by 5.1.

**What Story 5.3 explicitly deferred to this story:**
- SSE / real-time updates
- Approve/Reject buttons
- Auto-refresh every 5s
- NotificationBadge in navigation
- Rollback action trigger (though rollback trigger button rendering can begin here)

### Backend API Contracts (Already Implemented in Epic 3)

All backend endpoints are fully built and tested. The frontend consumes them:

**POST /api/v1/incidents/{id}/approve**
- Auth: Bearer token required
- Returns on success: `{ data: { status: "approved", new_state: "executing" }, meta: {...} }`
- Returns 409 if: not in `awaiting_approval` state, no plan exists, minimum review time not elapsed
- 409 body for review time: `{ error: "Minimum review time has not elapsed", code: "CONFLICT", detail: { review_time_remaining: 42.5 } }`

**POST /api/v1/incidents/{id}/reject**
- Auth: Bearer token required
- Body: `{ reason: string }` (non-empty required)
- Returns on success: `{ data: { status: "rejected", new_state: "failed" }, meta: {...} }`
- Returns 409 if: not in `awaiting_approval` state, no plan exists

**GET /api/v1/incidents/awaiting-approval**
- Returns: `{ data: [{ id, state, severity, blast_radius, created_at, updated_at }], meta: { total: N } }`
- Only incidents in `awaiting_approval` state

**GET /api/v1/events/stream (SSE)**
- Returns `text/event-stream` with events:
  - `id: {monotonic_int}\nevent: {event_name}\ndata: {json}\n\n`
  - Event names: `incident.created`, `incident.stage_changed`, `incident.state_changed`, `incident.resolved`, `incident.approval_decision`
  - Data envelope: `{ incident_id, stage, state, timestamp, payload }`
- Supports `Last-Event-ID` header for reconnection replay
- Sends `: keepalive\n\n` every 15s
- Auth: Bearer token required (via header on initial connection)

**POST /api/v1/incidents/{id}/rollback**
- Available when state is `resolved` or `failed` and execution log exists
- Returns: `{ data: { status: "rolled_back" }, meta: {...} }`

### SSE Implementation Strategy

Native `EventSource` does NOT support custom headers (Authorization). Two options:

**Option A (Recommended): fetch-based SSE using `@microsoft/fetch-event-source` or manual implementation**
```typescript
import { fetchEventSource } from '@microsoft/fetch-event-source';

fetchEventSource('/api/v1/events/stream', {
  headers: { Authorization: `Bearer ${getToken()}` },
  onmessage(ev) { /* handle event */ },
  onclose() { /* reconnect logic */ },
  onerror(err) { /* backoff logic */ },
});
```

**Option B: Pass token as query param (less secure, simpler)**
Not recommended — tokens in URLs leak via logs and referrer headers.

**Use Option A.** If `@microsoft/fetch-event-source` is not desired, implement a minimal fetch-based SSE reader using `ReadableStream`:
```typescript
async function* sseStream(url: string, token: string) {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
  });
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  // Parse SSE frames from buffer...
}
```

### Reconnection with Exponential Backoff

Per project-context.md:
- Initial delay: 1s
- Max delay: 30s
- Jitter: add random 0–500ms to prevent thundering herd
- On each failure: `delay = min(delay * 2, 30000) + random(0, 500)`
- On success: reset delay to 1s
- Include `Last-Event-ID` header with last received event ID for replay

### TanStack Query Patterns for Mutations

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query';

export function useApproveIncident(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/v1/incidents/${incidentId}/approve`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!response.ok) {
        const error = await response.json();
        throw error;
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents', incidentId] });
      queryClient.invalidateQueries({ queryKey: ['incidents-awaiting'] });
    },
  });
}
```

### NotificationBadge Implementation

PatternFly 6 `NotificationBadge` usage:
```typescript
import { NotificationBadge } from '@patternfly/react-core';

<NavItem>
  Incidents
  {awaitingCount > 0 && (
    <NotificationBadge
      variant="attention"
      count={awaitingCount}
      aria-label={`${awaitingCount} incidents awaiting approval`}
    />
  )}
</NavItem>
```

**Important:** Check the PF6 API — if `NotificationBadge` doesn't support inline in a `NavItem`, use a `Badge` component with `isRead={false}` variant instead. Verify the PatternFly docs for the correct component and props.

### Minimum Review Time Handling

When `POST /approve` returns 409 with `review_time_remaining`:
- Parse `detail.review_time_remaining` (seconds) from the error response
- Show the Approve button in a disabled state with tooltip: "Review time remaining: {n}s"
- Optionally show a live countdown using `setInterval` (visual-only, re-attempt after countdown)
- The countdown is NOT required for AC — a simple disabled state with explanatory tooltip suffices

### Rejection Modal Pattern

```typescript
import { Modal, ModalVariant, TextArea, Button } from '@patternfly/react-core';

<Modal
  variant={ModalVariant.small}
  title="Reject Remediation Plan"
  isOpen={isRejectModalOpen}
  onClose={() => setIsRejectModalOpen(false)}
  actions={[
    <Button
      key="reject"
      variant="danger"
      onClick={handleReject}
      isDisabled={!rejectReason.trim()}
      isLoading={rejectMutation.isPending}
    >
      Reject
    </Button>,
    <Button key="cancel" variant="link" onClick={() => setIsRejectModalOpen(false)}>
      Cancel
    </Button>,
  ]}
>
  <TextArea
    aria-label="Rejection reason"
    value={rejectReason}
    onChange={(_ev, val) => setRejectReason(val)}
    isRequired
    placeholder="Explain why this remediation plan should not proceed..."
  />
</Modal>
```

### Directory Structure (Files Created/Modified in This Story)

```
frontend/src/
  hooks/
    use-sse.ts                              [NEW] — Shared SSE connection hook with reconnect
    use-sse.test.ts                         [NEW] — Unit tests for SSE hook
  features/incidents/
    hooks/
      use-approve-incident.ts               [NEW] — useMutation for approve
      use-reject-incident.ts                [NEW] — useMutation for reject
      use-awaiting-approval-count.ts        [NEW] — useQuery for awaiting count
      use-incident-sse.ts                   [NEW] — Wires SSE to query invalidation
    components/
      remediation-panel.tsx                 [UPDATE] — Add approve/reject buttons + reject modal
      remediation-panel.test.tsx            [UPDATE] — Add tests for approval actions
      approval-actions.tsx                  [NEW] — Approve/Reject button group + modal (extracted)
      approval-actions.test.tsx             [NEW] — Unit tests
    pages/
      incident-detail.tsx                   [UPDATE] — Wire useIncidentSSE, polling fallback
      incident-detail.test.tsx              [UPDATE] — Add SSE/polling tests
  app/
    app.tsx (or nav component)              [UPDATE] — Add NotificationBadge to Incidents nav item
    app.test.tsx                            [UPDATE] — Test badge rendering
  mocks/
    handlers.ts                             [UPDATE] — Add approve, reject, awaiting-approval handlers
```

### PatternFly Component Usage Map

| Feature | PatternFly Components |
|---|---|
| Approve button | `Button` (variant="primary") |
| Reject button | `Button` (variant="danger") |
| Rejection modal | `Modal` (ModalVariant.small), `TextArea`, `Button` |
| Navigation badge | `NotificationBadge` (variant="attention") or `Badge` |
| Error alert | `Alert` (variant="danger", isInline) |
| Polling indicator | `Label` (isCompact, variant="info") — "Live updates paused" |
| Loading state on button | `Button` with `isLoading` prop |

### Accessibility Requirements

- **Approve button:** `aria-label="Approve remediation plan"` or use visible text (PF Button with text is already accessible)
- **Reject button:** `aria-label="Reject remediation plan"`
- **Both buttons:** `aria-describedby` linking to the remediation plan summary (per UX-DR19) so screen reader users get context before acting
- **NotificationBadge:** `aria-label="{n} incidents awaiting approval"` — count must be announced, not just visually displayed
- **Modal:** PatternFly Modal handles focus trap and aria automatically — ensure `title` prop is set
- **SSE connection indicator:** `role="status"` with `aria-live="polite"` so screen readers announce connection state changes

### SSE Testing Strategy

SSE cannot be easily tested with MSW (MSW 2.x has limited SSE support). Two approaches:

**For unit tests of the SSE hook:**
- Create a `MockEventSource` helper or mock `fetch` at the `ReadableStream` level
- Test: connection establishment, event parsing, reconnection logic, cleanup on unmount

**For integration tests of SSE-driven UI updates:**
- Mock the `useSSE` hook to expose a `simulateEvent()` function
- Test that simulated events trigger query invalidation and UI re-render
- Verify: approval decision event decrements badge, stage change event updates stepper

### Project Structure Notes

- `use-sse.ts` goes in shared `hooks/` (not feature-specific) because SSE is used by multiple features and the connection is shared per-app
- Approval mutation hooks go in `features/incidents/hooks/` as they are incident-feature-specific
- The `approval-actions.tsx` component is extracted from `remediation-panel.tsx` to keep file size manageable — it renders the button group + modal together
- No new provider abstraction needed — direct fetch in mutation hooks is fine (matching Story 5.3 pattern)

### Anti-Patterns / DO NOT

- **DO NOT** use native `EventSource` — it doesn't support Authorization headers. Use fetch-based SSE.
- **DO NOT** open one SSE connection per component — share ONE connection in the app via `useSSE` hook at the app shell level or via context
- **DO NOT** add confirmation modals for Approve action — per UX-DR12, single-click for standard blast radius
- **DO NOT** implement rollback trigger action flow — show "Rollback Available" indicator (from Story 5.3) but the actual POST /rollback is triggered from a future interaction
- **DO NOT** implement keyboard shortcut `a` for approve — that is Story 5.6
- **DO NOT** create a custom notification/toast system — use PatternFly's inline Alert for error feedback
- **DO NOT** use `setInterval` for polling — use TanStack Query's built-in `refetchInterval` option
- **DO NOT** use snapshot tests — forbidden per project rules
- **DO NOT** mock `fetch` directly — use MSW for API mocking; for SSE mock the stream
- **DO NOT** add Redux/Zustand for SSE state — React context or hook-level state is sufficient
- **DO NOT** implement statistics dashboard features — that is Story 5.5
- **DO NOT** implement policy adjustment UI — that's beyond this story scope
- **DO NOT** use custom hex colors or CSS — PatternFly tokens only
- **DO NOT** add animations to badge count changes — clinical calm

### Dependencies

This story depends on:
- **Story 5.3** (incident detail view) — provides the remediation panel component, pipeline stepper, page structure, `useIncidentDetail` hook
- **Story 5.1** (app shell) — provides the Nav sidebar component where NotificationBadge is added

If `@microsoft/fetch-event-source` is used, add it as a dependency:
```bash
npm install @microsoft/fetch-event-source
```

Alternatively, implement a minimal 50-line SSE reader using `fetch` + `ReadableStream` to avoid an external dependency.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5, Story 5.4] — acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR3] — NotificationBadge specification
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR12] — Approval button specification
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR20] — Auto-refresh 5s while active
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR21] — SSE subscription, polling fallback
- [Source: _bmad-output/project-context.md#SSE connection management] — reconnect rules
- [Source: _bmad-output/project-context.md#Frontend Architecture Decisions FA-3] — SSE strategy
- [Source: _bmad-output/project-context.md#TanStack Query for server state FA-2] — query invalidation
- [Source: backend/src/api/approval.py] — Approve/Reject/Awaiting endpoints
- [Source: backend/src/api/events.py] — SSE stream endpoint
- [Source: backend/src/api/event_bus.py] — Event bus with replay buffer
- [Source: backend/src/models/events.py] — SSEEventData envelope, EventNames
- [Source: backend/src/models/approval.py] — ApprovalContext, RejectionRequest
- [Source: _bmad-output/implementation-artifacts/5-3-incident-detail-view-and-pipeline-visualization.md] — predecessor patterns
- [Source: _bmad-output/implementation-artifacts/5-1-frontend-scaffolding-and-app-shell.md] — app shell, nav, providers

## Code Review Record

### Review Model Used

_(To be filled after review — must differ from dev model)_

### Review Findings

_(To be filled after review)_

### Decisions Needed / Decisions Taken

_(To be filled after review)_

### Fixes Applied

_(To be filled after review)_

## Dev Agent Record

### Agent Model Used

_(To be filled during development)_

### Debug Log References

### Completion Notes List

### File List
