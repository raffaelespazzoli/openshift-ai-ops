# Technology Verification Review

| Field | Value |
|-------|-------|
| Reviewed | 2026-08-06 |
| Spine | ARCHITECTURE-SPINE.md (2026-08-05) |
| Verdict | **PASS with 2 SHOULD-FIX items** |

---

## Stack Table Verification

| Technology | Pinned Version | Current Version (Aug 2026) | Tier | Notes |
|---|---|---|---|---|
| Python | ≥3.10 | 3.13.x stable | ✅ OK | LangGraph 1.2.x requires ≥3.10 per PyPI metadata. Verified. |
| LangGraph | 1.2.x | 1.2.10 (2026-07-28) | ✅ OK | Actively maintained. MIT license. Checkpoint persistence confirmed. |
| FastAPI | 0.141.x | 0.141.1 (2026-07-29) | ✅ OK | Latest release. Native SSE since 0.135.0. |
| PostgreSQL | 18.x | 18 (GA 2025-09-25) | ✅ OK | Current major release. PG 19 Beta 2 (2026-07-16) not yet stable. |
| pgvector | 0.8.x | 0.8.6 (2026-07-29) | ✅ OK | Actively maintained. Docker tag `pgvector/pgvector:0.8.6-pg18` exists. |
| kubernetes-mcp-server | 0.0.66+ | 0.0.66 (2026-08-04) | ✅ OK | Latest release. Go-based. Streamable HTTP via `--port` flag confirmed. `--read-only` flag confirmed. |
| React | 19.x | 19.2.8 (2026-07-21) | ✅ OK | Stable since Dec 2024. Actively maintained. |
| TypeScript | 7.x | 7.0 (2026-07-08) | ✅ OK | Go-native rewrite confirmed. 8–12x faster builds. "10x faster" claim accurate. |
| @patternfly/react-core | 6.6.x | 6.6.0 (Q3 2026) | ✅ OK | React 19 support confirmed (non-breaking, supports React 17/18/19). |
| Helm | 4.x | 4.2.3 (2026-07-08) | ✅ OK | Current stable release. Helm v3 in support mode (security-only until Nov 2026). |
| prometheus-client | 0.21.x | 0.26.0 (PyPI) / 0.25.0 (GitHub, 2026-04-09) | ⚠️ SHOULD-FIX | 0.21.x released Sep–Dec 2024. Five major versions behind. Still works but misses 18 months of fixes and features. |
| nginx | 1.27.x | 1.30.4 stable / 1.31.3 mainline | ⚠️ SHOULD-FIX | 1.27.x reached EOL June 2025 (>1 year ago). Multiple CVEs in superseding releases. Must update to 1.30.x (stable) or 1.31.x (mainline). |

---

## AD Fit-Claim Verification

| Claim (AD) | Verification | Tier |
|---|---|---|
| AD-8: "LangGraph/LLM ecosystem" justifies Python backend | LangGraph.js reached feature parity in Oct 2025, but Python LangGraph has 3× more LLM integrations (98 vs 33), 10× larger community (39k vs 2.6k stars), and all ML ecosystem tooling. Python choice remains well-justified. | ✅ OK |
| AD-8: "MCP Server is Go (external binary, not our code)" | Confirmed. `containers/kubernetes-mcp-server` is a Go-based native implementation (pkg.go.dev lists Go 1.26.3). Distributed as a single binary. | ✅ OK |
| AD-9: "Backend communicates with MCP servers via Streamable HTTP transport" | Confirmed. The `--port` flag starts both Streamable HTTP (`/mcp`) and SSE (`/sse`) listeners. Documented in README and Red Hat Developer article. | ✅ OK |
| AD-9: "stdio requires same-process; separate pods require network transport" | Accurate. stdio is IPC-only; Streamable HTTP is the recommended transport for remote/multi-pod deployments. | ✅ OK |
| AD-10: "FastAPI serves SSE endpoints" | Confirmed. Native SSE support added in FastAPI 0.135.0 (March 2026) via `fastapi.sse.EventSourceResponse`. No external library needed. | ✅ OK |
| AD-2: kubernetes-mcp-server `--read-only` flag | Confirmed. `--read-only` blocks all write operations. Documented on GitHub README. | ✅ OK |
| Stack: "TypeScript 7.x — Go-native rewrite, 10x faster builds" | Confirmed. Released 2026-07-08. Compiler rewritten from JS to Go. Shared-memory multithreading yields 8–12x speedups. | ✅ OK |
| Stack: PatternFly 6 requires React 19 | Partially accurate. PatternFly 6 *supports* React 19 but does not *require* it — it supports React 17, 18, and 19. The spine says "per PatternFly 6 compatibility" which is correctly framed as a compatibility choice rather than a hard requirement. | ℹ️ INFO |

---

## Findings Summary

### MUST-FIX

None.

### SHOULD-FIX

#### 1. nginx 1.27.x → update to 1.30.x or 1.31.x

- **Risk:** nginx 1.27 reached EOL in June 2025. It has not received security patches for over a year. Multiple CVEs (CVE-2026-42533, CVE-2026-60005, CVE-2026-56434, CVE-2026-42055, CVE-2026-48142, CVE-2026-42530, CVE-2026-9256) were addressed in newer branches that 1.27.x never received.
- **Fix:** Change `nginx | 1.27.x` to `nginx | 1.30.x` (current stable) in the Stack table.

#### 2. prometheus-client 0.21.x → update to ≥0.25.x

- **Risk:** Version 0.21.x was released September–December 2024. The library is now at 0.25.0 (April 2026) / 0.26.0 (PyPI). The pinned version is 5 minor versions behind and misses 18 months of bug fixes and improvements.
- **Fix:** Change `prometheus-client | 0.21.x` to `prometheus-client | 0.26.x` (or `≥0.25`) in the Stack table.

### INFO

#### 3. TypeScript 7.0 programmatic API not yet available

- TypeScript 7.0 ships the compiler binary only. The programmatic API (used by webpack loaders, Vue/Svelte template type-checking) is deferred to 7.1 (expected ~Oct 2026). This does not affect direct `tsc` compilation but may impact build tooling that imports the TypeScript compiler as a library. The `@typescript/typescript6` compatibility package bridges the gap.
- **Impact:** Low for this project (standard React/PatternFly frontend without exotic template transforms). Monitor for 7.1 release.

#### 4. LangGraph.js has reached feature parity with Python LangGraph

- The spine justifies Python via "fighting the LangGraph/LLM ecosystem" (AD-8). While historically accurate (LangGraph was Python-first), LangGraph.js reached 1.0 GA in October 2025 and now has full feature parity. The Python choice remains well-justified on ecosystem breadth (98 vs 33 model providers, larger community), but the "Python-first" framing is no longer technically precise.
- **Impact:** None — the decision is sound on other grounds. Consider softening the language from "fighting the ecosystem" to "leveraging the broader Python ML/AI ecosystem."

#### 5. PatternFly 6 supports React 17/18/19 — not exclusively React 19

- The stack note says React 19 is chosen "per PatternFly 6 compatibility." This is accurate as a motivation but could be misread as PatternFly 6 *requiring* React 19. PatternFly 6 supports React 17, 18, and 19.
- **Impact:** Cosmetic. The architecture's choice of React 19 is correct and future-proof.

---

## Methodology

Each technology was verified via web search on 2026-08-06 against:
- Official project websites and documentation
- GitHub release pages and changelogs
- PyPI / npm / pkg.go.dev package registries
- End-of-life tracking databases (endoflife.date, eol.wiki)

No claims were found to rely on stale training data or non-existent versions.

---

## Verdict

**PASS.** All named technologies exist, are actively maintained, and versions are real. Two version pins (nginx, prometheus-client) are outdated and should be bumped. No deprecated or non-existent technology was committed. All fit claims verified as accurate.
