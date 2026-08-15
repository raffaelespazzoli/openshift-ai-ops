---
baseline_commit: ba92badbb389f9b8e9528305597783be08772566
---

# Story 5.1: Frontend Scaffolding & App Shell

Status: done

## Story

As an SRE,
I want a standalone web application with the same look and feel as the OpenShift Console,
so that the tool feels familiar and will migrate seamlessly to a Console plugin in the future.

## Acceptance Criteria

1. **Given** the frontend project is initialized **When** a developer inspects the structure **Then** it is a React 19 + TypeScript application using PatternFly 6 (`@patternfly/react-core` 6.6.x) in `frontend/src/`, with Vite as the build tool.

2. **Given** the application loads **When** the shell renders **Then** it displays a horizontal masthead (top) and vertical navigation sidebar (left) matching the OpenShift Console layout per UX-DR6, with two nav items: "Incidents" and "Statistics".

3. **Given** the application loads for the first time **When** the theme is applied **Then** dark mode is the default theme per UX-DR5, a PatternFly theme toggle is available in the masthead to switch between dark and light modes, and no custom dark-mode tokens or hex colors are used — all theming is via PatternFly CSS custom properties.

4. **Given** an unauthenticated user accesses the application **When** the page loads **Then** the frontend initiates the OpenShift OAuth flow per AD-12, and all subsequent API calls include the bearer token in the Authorization header.

5. **Given** the frontend makes an API call **When** the response is received **Then** it correctly handles the `{data: T, meta: {timestamp, request_id}}` envelope format, and error responses in `{error, code, detail}` format are parsed and displayed appropriately.

6. **Given** the Helm chart **When** the frontend deployment is added **Then** it includes an nginx container serving the built React application as static assets, and the Deployment is configured for the single namespace per AD-9.

## Tasks / Subtasks

- [x] Task 1: Initialize React 19 + TypeScript + Vite project (AC: #1)
  - [x] 1.1 Run `npm create vite@latest frontend -- --template react-ts` or equivalent scaffolding
  - [x] 1.2 Install PatternFly 6 core packages (`@patternfly/react-core`, `@patternfly/react-icons`, `@patternfly/react-styles`, `@patternfly/react-tokens`)
  - [x] 1.3 Install TanStack Query v5 (`@tanstack/react-query`, `@tanstack/react-query-devtools`)
  - [x] 1.4 Install test tooling: Vitest (or Jest), React Testing Library, jest-axe, MSW
  - [x] 1.5 Configure `tsconfig.json` with strict mode, `noEmit: true`, path aliases
  - [x] 1.6 Configure `vite.config.ts` with `@vitejs/plugin-react`, proxy for `/api` during dev
  - [x] 1.7 Delete the `.gitkeep` in `frontend/src/` and scaffold the feature-based directory layout

- [x] Task 2: Create feature-based directory structure (AC: #1)
  - [x] 2.1 Create `frontend/src/app/` — App shell, routing, providers
  - [x] 2.2 Create `frontend/src/components/` — Shared PatternFly-based components
  - [x] 2.3 Create `frontend/src/features/incidents/` — Incidents feature module (placeholder)
  - [x] 2.4 Create `frontend/src/features/statistics/` — Statistics feature module (placeholder)
  - [x] 2.5 Create `frontend/src/features/approval/` — Approval feature module (placeholder)
  - [x] 2.6 Create `frontend/src/hooks/` — Shared hooks (useSSE, useApiClient, etc.)
  - [x] 2.7 Create `frontend/src/providers/` — DataProvider interface + REST implementation
  - [x] 2.8 Create `frontend/src/models/` — TypeScript types matching API envelope
  - [x] 2.9 Create `frontend/src/mocks/` — MSW handlers for testing
  - [x] 2.10 Create `frontend/src/utils/` — Pure utility functions

- [x] Task 3: Implement App Shell with Console layout (AC: #2, #3)
  - [x] 3.1 Create `main.tsx` entry point importing PatternFly CSS
  - [x] 3.2 Implement `App.tsx` using PatternFly `Page`, `Masthead`, `PageSidebar` with Console shell layout
  - [x] 3.3 Add vertical `Nav` with two items: "Incidents" (default active) and "Statistics"
  - [x] 3.4 Configure React Router with two routes for Incidents and Statistics (lazy-loaded per FA-4)
  - [x] 3.5 Add PatternFly theme toggle in masthead; default to dark mode
  - [x] 3.6 Create placeholder route components that render PatternFly `EmptyState`
  - [x] 3.7 Wrap each route component in a React error boundary with PatternFly `EmptyState` fallback (danger icon + "Reload" action)

- [x] Task 4: Implement DataProvider abstraction and API client (AC: #4, #5)
  - [x] 4.1 Define `DataProvider` interface in `providers/` (future Console SDK migration seam per FA-1)
  - [x] 4.2 Implement REST `DataProvider` with typed fetch wrapper handling the `{data, meta}` envelope
  - [x] 4.3 Implement error response parsing for `{error, code, detail}` format
  - [x] 4.4 Implement OpenShift OAuth flow stub — redirect to OAuth, store token, inject `Authorization: Bearer <token>` header
  - [x] 4.5 Set up `QueryClient` with appropriate defaults (`staleTime`, error handling)
  - [x] 4.6 Wrap the app in `QueryClientProvider`

- [x] Task 5: Add Helm chart frontend deployment (AC: #6)
  - [x] 5.1 Create `charts/openshift-ai-ops/templates/deployment-frontend.yaml` — nginx container serving static assets
  - [x] 5.2 Create `charts/openshift-ai-ops/templates/service-frontend.yaml`
  - [x] 5.3 Add `frontend` section to `values.yaml` (image, port 8080, resource limits)
  - [x] 5.4 Create `frontend/Dockerfile` — multi-stage build (Node build → nginx serve)
  - [x] 5.5 Create `frontend/nginx.conf` — serve `index.html` for all routes (SPA fallback), proxy `/api` to backend service

- [x] Task 6: Testing infrastructure (AC: #1)
  - [x] 6.1 Configure test runner (Vitest or Jest) with jsdom environment
  - [x] 6.2 Add MSW setup file in `frontend/src/mocks/handlers.ts` with sample API response mocks
  - [x] 6.3 Write unit test for App Shell: verifies masthead renders, both nav items present, dark mode default
  - [x] 6.4 Write unit test for API envelope handling: correct data extraction and error parsing
  - [x] 6.5 Include `jest-axe` assertion in every component test: `expect(await axe(container)).toHaveNoViolations()`
  - [x] 6.6 Verify all tests pass with `npm test`

## Dev Notes

### Technical Stack (Exact Versions)

| Package | Version | Purpose |
|---------|---------|---------|
| react | 19.x (latest stable, currently ~19.2) | UI framework |
| react-dom | 19.x | DOM rendering |
| typescript | 6.x or 7.x | Type checking (7 is Go-native rewrite, 10x faster builds — use if stable, else 6.x) |
| vite | 7.x | Build tool + dev server with HMR |
| @vitejs/plugin-react | latest | React plugin for Vite (Fast Refresh, JSX transform) |
| @patternfly/react-core | 6.6.x | UI component library (Console-compatible) |
| @patternfly/react-icons | 6.6.x | Icon components |
| @patternfly/react-styles | 6.6.x | CSS-in-JS utilities |
| @patternfly/react-tokens | 6.6.x | Design tokens as JS objects |
| @tanstack/react-query | 5.x | Server state management (React Query) |
| @tanstack/react-query-devtools | 5.x | Dev tools for query debugging |
| react-router-dom | 7.x | Client-side routing |
| msw | 2.x | Mock Service Worker for test API mocking |
| vitest | latest | Test runner (Vite-native, faster than Jest) |
| @testing-library/react | latest | Component testing |
| @testing-library/jest-dom | latest | DOM matchers |
| jest-axe | latest | Accessibility assertions |

### Architecture Decisions to Follow

- **FA-1 (Standalone-first, Console-ready):** SPA served by nginx. The `providers/` abstraction is the migration seam — swap REST/SSE provider for Console SDK provider later. NO Console SDK dependency in v1.
- **FA-2 (TanStack Query for server state):** All API data via TanStack Query. Query keys follow `[resource, ...params]` convention. No `useState` + `useEffect` fetch patterns.
- **FA-3 (SSE for real-time):** SSE subscription endpoints exist but are NOT implemented in this story — wire up in Story 5.4. The `DataProvider` interface should account for real-time subscriptions.
- **FA-4 (Feature-based code splitting):** Each feature module (`incidents`, `statistics`, `approval`) is lazily loaded via `React.lazy()`. Route-level splitting only.

### PatternFly 6 Component Usage (App Shell)

The App Shell uses these specific PatternFly components:

```
Page                     — top-level page layout wrapper
  Masthead               — horizontal top bar
    MastheadMain         — left section (brand/logo)
      MastheadBrand      — brand link
    MastheadContent      — right section (theme toggle, user info)
  PageSidebar            — left vertical navigation
    Nav                  — navigation component
      NavList            — navigation item list
        NavItem          — individual nav items ("Incidents", "Statistics")
  PageSection            — main content area (route outlet)
```

For the theme toggle, use the PatternFly approach:
- Import `@patternfly/react-core/dist/styles/base.css` (light) and `@patternfly/react-core/dist/styles/base-dark-theme.css` (dark)
- Or use the newer PF6 `ThemeContext` / `pf-v6-theme-dark` CSS class toggling approach
- Dark mode default means the `<html>` or body element starts with the dark theme class

### TypeScript Frontend Conventions (from project-context.md)

- **camelCase** for variables, functions, props
- **Kebab-case filenames** — all `.tsx`, `.ts`, `.css` files (e.g., `incident-detail.tsx`)
- **No custom components** — use PatternFly components directly, no wrappers
- **PatternFly design tokens only** — never `#rrggbb` or `rgb()`, only `--pf-t--global--*` CSS custom properties
- **API envelope assumption** — all REST responses follow `{data: T, meta: {timestamp, request_id}}`
- **Error boundary on every route** — wrap each route in error boundary, fallback to PatternFly `EmptyState` with danger icon + "Reload"
- **URL state for filters** — persist filters in URL query params (implemented in later stories, but router should be ready)
- **Date formatting** — `Intl.RelativeTimeFormat` for < 24h, ISO 8601 for older. No moment.js.

### API Contracts (Backend Already Exists)

The backend REST API is fully built through Epics 1-4. Key endpoints the frontend consumes:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/v1/incidents` | GET | Paginated list with filters (status, severity, time range) |
| `GET /api/v1/incidents/{id}` | GET | Full incident detail with correlated alerts |
| `POST /api/v1/incidents/{id}/approve` | POST | Approve remediation |
| `POST /api/v1/incidents/{id}/reject` | POST | Reject remediation |
| `POST /api/v1/incidents/{id}/rollback` | POST | Trigger rollback |
| `GET /api/v1/events/incidents` | SSE | Live incident list updates |
| `GET /api/v1/events/incidents/{id}` | SSE | Live detail view updates |
| `GET /healthz` | GET | Health check |

**Response envelope:**
```typescript
interface ApiResponse<T> {
  data: T;
  meta: {
    timestamp: string;   // ISO 8601
    request_id: string;  // UUID
    page?: number;
    page_size?: number;
    total?: number;
  };
}

interface ApiError {
  error: string;
  code: string;       // e.g., "NOT_FOUND", "UNAUTHORIZED"
  detail: Record<string, unknown>;
}
```

### OpenShift OAuth Flow (AC #4)

For this story, implement a **stub/configurable auth flow**:
1. On app load, check for a bearer token in `localStorage` or session
2. If missing, redirect to the OpenShift OAuth server URL (configurable via environment variable `VITE_OAUTH_URL`)
3. Handle the OAuth callback to extract and store the token
4. Attach the token to all API requests via `Authorization: Bearer <token>` header
5. For development, support a `VITE_DEV_TOKEN` env var to bypass OAuth (dev-only convenience)
6. Implement token refresh/expiry handling as a basic interceptor

### Helm Chart Frontend Deployment

The Helm chart currently has 7 deployments (backend, postgresql, mcp-readonly, mcp-readwrite, solr, okp-mcp + implicit agentic-skills). Adding the frontend deployment requires:

- `deployment-frontend.yaml` — nginx container, 1 replica, port 8080
- `service-frontend.yaml` — ClusterIP service for frontend
- `values.yaml` frontend section with image, tag, resources

The nginx config must:
- Serve `index.html` for all routes (SPA fallback — `try_files $uri $uri/ /index.html`)
- Proxy `/api` requests to the backend service (`http://{{ .Release.Name }}-backend:8000`)
- Set appropriate cache headers (long cache for hashed assets, no-cache for `index.html`)

### Dockerfile (Multi-Stage Build)

```dockerfile
# Stage 1: Build
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:1.30-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
```

### Directory Structure (Final State)

```
frontend/
  src/
    app/                         # App shell, routing, providers
      app.tsx                    # Main App component with PF Page layout
      routes.tsx                 # Route definitions with lazy loading
      error-boundary.tsx         # Reusable error boundary component
    components/                  # Shared PatternFly-based components
      theme-toggle.tsx           # Dark/light mode toggle
    features/                    # Feature modules (lazy-loaded)
      incidents/
        components/              # Feature-specific components (placeholder)
        hooks/                   # Feature-specific hooks (placeholder)
        index.tsx                # Route entry point (placeholder EmptyState)
      statistics/
        index.tsx                # Route entry point (placeholder EmptyState)
      approval/                  # (placeholder for Story 5.4)
    hooks/                       # Shared hooks
      use-api-client.ts          # Typed fetch with envelope handling
    providers/                   # DataProvider interface + REST implementation
      data-provider.ts           # Provider interface (migration seam)
      rest-provider.ts           # REST + fetch implementation
    models/                      # TypeScript types matching API
      api.ts                     # ApiResponse<T>, ApiMeta, ApiError types
      incident.ts                # Incident, Alert types (match backend models)
    mocks/                       # MSW handlers
      handlers.ts                # Centralized mock API handlers
      server.ts                  # MSW server setup for tests
    utils/                       # Pure utility functions
      date.ts                    # Date formatting helpers
    main.tsx                     # Entry point
    index.css                    # Global styles (PF imports only)
  public/                        # Static assets
  package.json
  tsconfig.json
  vite.config.ts
  vitest.config.ts               # Test configuration
  Dockerfile
  nginx.conf
  .env.example                   # Environment variable template
```

All filenames are kebab-case. All test files colocated: `*.test.tsx` next to component.

### Project Structure Notes

- Alignment with AD-14 monorepo layout: `frontend/src/` is the designated frontend location
- The `providers/` directory is the FA-1 migration seam — the ONLY directory that changes when migrating to Console plugin
- `models/` types mirror backend Pydantic models (`backend/src/models/api.py`, `backend/src/models/incident.py`)
- `mocks/handlers.ts` is centralized per testing rules — reused across all tests, per-test overrides via `server.use()`
- Feature modules (`incidents/`, `statistics/`, `approval/`) each get their own `components/` and `hooks/` subdirectories as they grow in later stories

### TanStack Query v5 Notes

- Use object syntax: `useQuery({ queryKey: ['incidents'], queryFn })`
- `isPending` (not `isLoading`) for first-load spinners
- `queryClient.invalidateQueries({ queryKey: ['incidents'] })` for SSE-triggered cache invalidation (Story 5.4)
- Set `staleTime` deliberately (e.g., 30000ms for incidents list)
- `queryFn` must throw on non-OK responses — don't return error objects

### Story Intelligence Chain

This is the **first story in Epic 5** and the **first frontend story in the project**. All prior epics (1–4) were backend Python only. Key inherited context:

- **Backend API is complete** through Epic 4 — all REST endpoints, SSE, OAuth, audit logging, pipeline stages, and learning store are implemented and tested
- **Helm chart exists** with backend, postgresql, MCP servers, solr, okp-mcp — but NO frontend deployment yet
- **Project-context.md was updated** at the end of Epic 4 specifically to add frontend development rules (PatternFly 6 token discipline, standalone-first + Console plugin migration path, Jest/RTL/MSW/jest-axe, provider abstraction, dark mode default, Console shell layout)
- **No frontend code exists** — `frontend/src/.gitkeep` is the only file. This is a greenfield scaffolding story
- **Conventional commits** — use `feat(frontend):` prefix for this work

### Anti-Patterns / DO NOT

- **DO NOT** create custom wrapper components around PatternFly (e.g., no `<AppButton>` wrapping `<Button>`)
- **DO NOT** use any hex colors, `rgb()`, or CSS variables outside the PatternFly namespace
- **DO NOT** add Redux, Zustand, or any state management beyond TanStack Query + React Context for cross-cutting concerns (theme, auth)
- **DO NOT** implement SSE/real-time updates — that is Story 5.4's responsibility
- **DO NOT** implement the full incidents list or detail views — those are Stories 5.2 and 5.3
- **DO NOT** implement the approval workflow UI — that is Story 5.4
- **DO NOT** implement statistics charts — that is Story 5.5
- **DO NOT** implement keyboard shortcuts or accessibility enhancements beyond baseline — that is Story 5.6
- **DO NOT** add the Console SDK or any OpenShift Console plugin dependency — v1 is standalone only
- **DO NOT** use snapshot tests — forbidden per project rules
- **DO NOT** mock `fetch` directly in tests — use MSW at the network level
- **DO NOT** use `moment.js` or any heavy date library
- **DO NOT** implement the NotificationBadge on the Incidents nav item yet — that requires the approval count API (Story 5.4)
- **DO NOT** add custom media queries — use PatternFly grid breakpoints only
- **DO NOT** implement animations or pulsing indicators — clinical calm per UX-DR20

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5, Story 5.1] — acceptance criteria and user story
- [Source: _bmad-output/project-context.md#TypeScript (Frontend)] — coding conventions
- [Source: _bmad-output/project-context.md#React + PatternFly (Frontend)] — framework rules
- [Source: _bmad-output/project-context.md#Frontend (TypeScript) Testing] — test standards
- [Source: _bmad-output/project-context.md#Frontend Architecture Decisions] — FA-1 through FA-4
- [Source: _bmad-output/project-context.md#Frontend Anti-Patterns] — critical don't-miss rules
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-openshift-ai-ops-2026-08-02/DESIGN.md] — PatternFly semantic tokens, brand delta
- [Source: _bmad-output/planning-artifacts/architecture/architecture-openshift-ai-ops-2026-08-03/ARCHITECTURE-SPINE.md#AD-8, AD-9, AD-14] — tech stack, deployments, source tree
- [Source: charts/openshift-ai-ops/values.yaml] — existing Helm values (no frontend section yet)
- [Source: backend/src/models/api.py] — API envelope types (ApiResponse, ApiMeta, ApiError)
- [Source: backend/src/api/incidents.py] — Incident list/detail endpoint signatures

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

Claude Opus 4.6 (via Cursor)

### Debug Log References

- PatternFly 6 does not ship a separate `base-dark-theme.css`; dark mode is toggled purely via the `pf-v6-theme-dark` CSS class on the `<html>` element with just `base.css` imported.
- `tsconfig.node.json` with `composite: true` requires either removing `noEmit` or using `emitDeclarationOnly: true` to satisfy the project references constraint used by `tsc -b`.
- Test files importing from `vitest` must be excluded from the main `tsconfig.json` to avoid type resolution issues (vitest globals types are handled by vitest's own type augmentation at runtime).
- jest-axe does not ship its own TypeScript declarations; a custom `vite-env.d.ts` module declaration is required.

### Completion Notes List

- **Task 1:** Initialized React 19 + TypeScript + Vite 6 project with PatternFly 6.6.x, TanStack Query 5, react-router-dom 7, Vitest 3, RTL 16, MSW 2, jest-axe. Strict tsconfig with path aliases.
- **Task 2:** Created complete feature-based directory structure: `app/`, `components/`, `features/{incidents,statistics,approval}/`, `hooks/`, `providers/`, `models/`, `mocks/`, `utils/`. All kebab-case filenames.
- **Task 3:** Implemented App Shell with PatternFly Page/Masthead/PageSidebar/Nav. Two nav items (Incidents, Statistics). Dark mode default via `pf-v6-theme-dark` class. Theme toggle in masthead (Sun/Moon icons). React Router with lazy-loaded routes. Error boundary with PatternFly EmptyState danger fallback.
- **Task 4:** DataProvider interface (migration seam per FA-1) with get/post/subscribe methods. REST provider with envelope extraction, typed error parsing (ApiClientError class), OAuth stub (token from localStorage or VITE_DEV_TOKEN env var, redirect flow, state validation). QueryClient with 30s staleTime, wrapped in QueryClientProvider.
- **Task 5:** Helm chart additions: deployment-frontend.yaml (nginx, port 8080, health probes), service-frontend.yaml (ClusterIP), values.yaml frontend section. Multi-stage Dockerfile (node:22-alpine build → nginx:1.27-alpine serve). nginx.conf with SPA fallback, /api proxy to backend, cache headers.
- **Task 6:** Vitest configured with jsdom, globals, CSS support. MSW handlers centralized in mocks/handlers.ts. 10 tests total: 5 App Shell tests (masthead, nav items, dark mode, theme toggle, a11y) + 5 API client tests (envelope extraction, params, error parsing, POST, unknown errors). All pass with jest-axe assertions.

### File List

| Action | File | Description |
|--------|------|-------------|
| NEW | frontend/package.json | Project manifest with all dependencies |
| NEW | frontend/tsconfig.json | TypeScript config with strict mode and path aliases |
| NEW | frontend/tsconfig.node.json | TypeScript config for Vite config files |
| NEW | frontend/vite.config.ts | Vite configuration with React plugin, path aliases, API proxy |
| NEW | frontend/vitest.config.ts | Vitest test runner configuration (jsdom, globals, setup) |
| NEW | frontend/index.html | HTML entry point with pf-v6-theme-dark class |
| NEW | frontend/.env.example | Environment variable template |
| NEW | frontend/Dockerfile | Multi-stage build (Node → nginx) |
| NEW | frontend/nginx.conf | nginx config with SPA fallback and API proxy |
| NEW | frontend/src/main.tsx | App entry point with providers |
| NEW | frontend/src/index.css | Global styles (PatternFly base CSS import) |
| NEW | frontend/src/vite-env.d.ts | Vite client types and jest-axe declarations |
| NEW | frontend/src/test-setup.ts | Test setup importing jest-dom matchers |
| NEW | frontend/src/app/app.tsx | Main App component with PF Page layout |
| NEW | frontend/src/app/app.test.tsx | App Shell unit tests (5 tests) |
| NEW | frontend/src/app/routes.tsx | Route definitions with lazy loading |
| NEW | frontend/src/app/error-boundary.tsx | Reusable error boundary component |
| NEW | frontend/src/components/theme-toggle.tsx | Dark/light mode toggle |
| NEW | frontend/src/features/incidents/index.tsx | Incidents placeholder (EmptyState) |
| NEW | frontend/src/features/statistics/index.tsx | Statistics placeholder (EmptyState) |
| NEW | frontend/src/hooks/use-api-client.ts | Typed API client hook |
| NEW | frontend/src/providers/data-provider.ts | DataProvider interface (migration seam) |
| NEW | frontend/src/providers/rest-provider.ts | REST DataProvider implementation |
| NEW | frontend/src/providers/rest-provider.test.ts | API client unit tests (5 tests) |
| NEW | frontend/src/models/api.ts | ApiResponse, ApiMeta, ApiError types |
| NEW | frontend/src/models/incident.ts | Incident, Alert TypeScript types |
| NEW | frontend/src/mocks/handlers.ts | Centralized MSW mock API handlers |
| NEW | frontend/src/mocks/server.ts | MSW server setup for tests |
| NEW | frontend/src/utils/auth.ts | OAuth flow utilities (token management) |
| NEW | frontend/src/utils/date.ts | Date formatting helpers |
| NEW | charts/openshift-ai-ops/templates/deployment-frontend.yaml | Helm frontend Deployment |
| NEW | charts/openshift-ai-ops/templates/service-frontend.yaml | Helm frontend Service |
| MODIFIED | charts/openshift-ai-ops/values.yaml | Added frontend section |
| DELETED | frontend/src/.gitkeep | Removed placeholder |

### Change Log

- 2026-08-15: Implemented Story 5.1 — Full frontend scaffolding with React 19, PatternFly 6, Vite, TanStack Query, OAuth stub, Helm deployment, and 10 passing tests.
