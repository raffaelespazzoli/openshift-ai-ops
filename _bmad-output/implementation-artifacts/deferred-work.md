## Deferred from: code review of 2-1-langgraph-diagnosis-pipeline-and-mcp-integration.md (2026-08-09)

- Story 2.1 MCP behavior appeared internally contradictory during review, but product scope was clarified for this re-review: Story 2.1 is infrastructure-only, the `diagnose_node` stub is intentional, and live MCP-backed diagnosis is deferred to Story 2.2.

## Deferred from: code review of 4-1-case-record-persistence-and-vector-embeddings (2026-08-14)

- Duplicate case record creation block in `execution_dispatcher.py` — identical try/except blocks in `_run_execution_cycle()` and `_run_recovery_observation()` could be extracted to a shared helper function. Pre-existing pattern, low priority.

## Deferred from: code review of 5-4-approval-workflow-and-real-time-updates (2026-08-15)

- No 401 differentiation in SSE reconnect (`use-sse.ts:74-75`) — SSE reconnect treats 401 the same as other errors, causing infinite backoff retries on expired tokens. Auth interceptor is an app-level concern beyond story 5.4's scope.
- No optimistic update on Approve/Reject (`use-approve-incident.ts`, `use-reject-incident.ts`) — Task 1.4 mentions "optimistic UI transition" but cache invalidation is functionally correct. Optimistic updates add complexity for marginal UX gain.

## Deferred from: code review of 5-6-keyboard-shortcuts-and-accessibility (2026-08-15)

- AC#7 aria-label uses state/severity instead of RCE label and alert count — The IncidentListItem model from Story 5.2 doesn't expose RCE group labels or correlated alert counts on list items. The AC assumes RCE-grouped data but the implemented model shows individual incidents with state/severity. Requires Story 5.2 data model extension to satisfy AC#7 fully.
