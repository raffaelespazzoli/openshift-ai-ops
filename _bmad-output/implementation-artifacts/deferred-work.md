## Deferred from: code review of 2-1-langgraph-diagnosis-pipeline-and-mcp-integration.md (2026-08-09)

- Story 2.1 MCP behavior appeared internally contradictory during review, but product scope was clarified for this re-review: Story 2.1 is infrastructure-only, the `diagnose_node` stub is intentional, and live MCP-backed diagnosis is deferred to Story 2.2.

## Deferred from: code review of 4-1-case-record-persistence-and-vector-embeddings (2026-08-14)

- Duplicate case record creation block in `execution_dispatcher.py` — identical try/except blocks in `_run_execution_cycle()` and `_run_recovery_observation()` could be extracted to a shared helper function. Pre-existing pattern, low priority.
