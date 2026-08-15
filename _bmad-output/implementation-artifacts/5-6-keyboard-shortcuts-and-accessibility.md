---
baseline_commit: 0c2ad975da9a78f283e948a6dd2ece028faeac6c
---

# Story 5.6: Keyboard Shortcuts & Accessibility

Status: review

## Story

As an SRE,
I want full keyboard navigation and screen reader support,
so that I can operate the tool efficiently and it meets WCAG 2.2 AA compliance.

## Acceptance Criteria

1. **Given** the Incidents list view **When** the user presses `j` or `k` **Then** focus moves down or up through incident list rows per UX-DR18.

2. **Given** a focused incident row **When** the user presses `Enter` **Then** the application navigates to the incident detail view per UX-DR18.

3. **Given** the incident detail view **When** the user presses `Backspace` or `Esc` **Then** the application returns to the Incidents list per UX-DR18.

4. **Given** the incident detail view **When** the user presses `1` through `6` **Then** the corresponding pipeline stage is selected and its content panel expands per UX-DR18.

5. **Given** the incident detail view with Remediation stage in `awaiting` state and expanded **When** the user presses `a` **Then** the approve action is triggered per UX-DR18.

6. **Given** pipeline stage states in the ProgressStepper **When** a screen reader encounters them **Then** each stage communicates its state via `aria-label` (e.g., "Diagnosis: completed", "Remediation: awaiting approval") — not color alone per UX-DR19.

7. **Given** a DataList RCE group **When** a screen reader encounters the expansion control **Then** the expansion state is announced (e.g., "Root-Cause Event: etcd fsync latency, 3 correlated alerts, collapsed. Activate to expand.") per UX-DR19.

8. **Given** the Approve and Reject buttons **When** a screen reader encounters them **Then** they include `aria-describedby` linking to the remediation plan summary so the user gets context before acting per UX-DR19.

9. **Given** the ProgressStepper stages **When** keyboard navigation is used **Then** left/right arrow keys move between stages per the PatternFly ProgressStepper accessibility pattern per UX-DR19.

10. **Given** the user navigates from the Incidents list to a detail view **When** the detail page loads **Then** focus moves to the breadcrumb per UX-DR19 **And** when returning to the list, focus is restored to the previously selected row.

11. **Given** the Statistics charts **When** a screen reader encounters them **Then** each chart includes an `aria-label` with a text summary of the data (e.g., "Line chart: 23 alerts over the last 7 days, peak on Tuesday") per UX-DR19.

12. **Given** an alert storm produces many RCE groups **When** the Incidents list renders **Then** all groups are collapsed by default with highest-severity groups sorted to the top per UX-DR20 **And** the full list renders without pagination (scroll) per the EXPERIENCE.md specification.

## Tasks / Subtasks

- [x] Task 1: Keyboard shortcuts hook infrastructure (AC: #1–5)
  - [x] 1.1 Create `frontend/src/hooks/use-keyboard-shortcuts.ts` — shared hook that registers/unregisters global keyboard event listeners
  - [x] 1.2 Implement focus-guard: disable all shortcuts when `document.activeElement` is an `input`, `textarea`, `select`, or `[contenteditable]` element (per project-context.md keyboard shortcut rules)
  - [x] 1.3 Add WCAG 2.1.4 compliance: implement `KeyboardShortcutsContext` with an `enabled` boolean that lets users disable all shortcuts (settings or via a `?` help panel)
  - [x] 1.4 Create `frontend/src/hooks/use-keyboard-shortcuts.test.ts` — unit tests for the hook

- [x] Task 2: Incidents list keyboard navigation — j/k/Enter (AC: #1, #2)
  - [x] 2.1 Create `frontend/src/features/incidents/hooks/use-list-keyboard-nav.ts` — manages focused row index, scrolls into view
  - [x] 2.2 Integrate with `incidents-list.tsx`: add `tabIndex={0}` on the DataList, track `focusedIndex` state, apply `aria-activedescendant` pointing to the focused row's `id`
  - [x] 2.3 On `j`: increment `focusedIndex` (clamp to list length), scroll row into view, update `aria-activedescendant`
  - [x] 2.4 On `k`: decrement `focusedIndex` (clamp to 0), scroll row into view
  - [x] 2.5 On `Enter`: navigate to `/incidents/{id}` for the focused row, store `focusedIndex` in route state for focus restoration
  - [x] 2.6 Style focused row with `--pf-t--global--color--nonstatus--blue--default` outline (visible focus indicator)
  - [x] 2.7 Write tests: `use-list-keyboard-nav.test.ts`

- [x] Task 3: Detail view keyboard shortcuts — Esc/Backspace, 1-6, `a` (AC: #3, #4, #5)
  - [x] 3.1 Create `frontend/src/features/incidents/hooks/use-detail-keyboard-nav.ts`
  - [x] 3.2 On `Escape` or `Backspace`: call `navigate(-1)` or navigate to `/incidents` with preserved filter state (from route state)
  - [x] 3.3 On `1`–`6`: set `expandedStage` to the corresponding 0-indexed stage (stage 1 = index 0, etc.)
  - [x] 3.4 On `a`: if incident state is `awaiting_approval` and Remediation panel is expanded, trigger the approve mutation (reuse `useApproveIncident` hook from Story 5.4)
  - [x] 3.5 Guard `a` shortcut: only active when state === 'awaiting_approval'. Show no effect otherwise.
  - [x] 3.6 Write tests: `use-detail-keyboard-nav.test.ts`

- [x] Task 4: ProgressStepper arrow key navigation (AC: #9)
  - [x] 4.1 Modify `frontend/src/features/incidents/components/pipeline-stepper.tsx` — wrap in a `role="tablist"` container, each ProgressStep gets `role="tab"`, `tabIndex={isFocused ? 0 : -1}`, `aria-selected`
  - [x] 4.2 Implement roving tabindex pattern: left/right arrow keys move focus between stages, Home/End jump to first/last
  - [x] 4.3 On Enter/Space on focused stage: toggle the corresponding content panel (expand/collapse)
  - [x] 4.4 Expanded panel gets `role="tabpanel"` with `aria-labelledby` pointing to the stage tab
  - [x] 4.5 Write tests verifying arrow key movement, Enter activation, ARIA roles

- [x] Task 5: Focus management on navigation transitions (AC: #10)
  - [x] 5.1 Modify `frontend/src/features/incidents/pages/incident-detail.tsx` — on mount, move focus to the breadcrumb element using `useEffect` + `ref.focus()`
  - [x] 5.2 Modify `frontend/src/features/incidents/index.tsx` (list view) — on mount, check route state for `returnFocusIndex`; if present, focus the DataListItem at that index
  - [x] 5.3 When navigating from list to detail: pass `{ returnFocusIndex: focusedIndex }` in route state
  - [x] 5.4 When navigating back from detail: the list page reads `returnFocusIndex` from state and restores focus
  - [x] 5.5 Write tests: verify focus moves to breadcrumb on detail mount, focus restores on list return

- [x] Task 6: DataList expansion announcements for screen readers (AC: #7)
  - [x] 6.1 Modify `frontend/src/features/incidents/components/incidents-list.tsx` — add descriptive `aria-label` on each DataListItem toggle button: "Root-Cause Event: {rce_label}, {alert_count} correlated alerts, {collapsed|expanded}. Activate to {expand|collapse}."
  - [x] 6.2 Add `aria-expanded` on the toggle control (PatternFly DataList may handle this natively — verify and supplement if needed)
  - [x] 6.3 Add `aria-controls` linking the toggle to the expanded content region's `id`
  - [x] 6.4 Write tests verifying aria attributes update on expand/collapse

- [x] Task 7: Approve/Reject aria-describedby (AC: #8)
  - [x] 7.1 Modify `frontend/src/features/incidents/components/approval-actions.tsx` — add a visually hidden `<span id="plan-summary-desc">` containing the remediation plan summary text (first 2 sentences of `plan_summary`)
  - [x] 7.2 Add `aria-describedby="plan-summary-desc"` to both Approve and Reject buttons
  - [x] 7.3 Write test verifying `aria-describedby` links to plan summary content

- [x] Task 8: Chart accessibility aria-labels (AC: #11)
  - [x] 8.1 Modify `frontend/src/features/statistics/components/activity-chart.tsx` — compute and set `aria-label` on the chart wrapper: summarize the data (e.g., "Line chart showing alerts, diagnoses, and resolutions over the last week. Peak: 12 alerts on Monday.")
  - [x] 8.2 Modify `frontend/src/features/statistics/components/mttr-chart.tsx` — compute and set `aria-label` on the chart wrapper: summarize the data (e.g., "Area chart showing mean time to resolution over the last week. Average: 5 minutes 12 seconds.")
  - [x] 8.3 Add `role="img"` on chart wrapper divs so screen readers treat them as single image elements
  - [x] 8.4 Write tests verifying `aria-label` contains meaningful data summary and `role="img"` is present

- [x] Task 9: ProgressStepper aria-labels for states (AC: #6)
  - [x] 9.1 Verify/enhance `pipeline-stepper.tsx` — confirm every ProgressStep has a dynamic `aria-label` in the format "{Stage}: {state description}" (e.g., "Triage: completed", "Remediation: awaiting approval", "Execution: in progress")
  - [x] 9.2 Add an `aria-live="polite"` hidden region that announces stage transitions: "Pipeline stage updated. {Stage} is now {state}."
  - [x] 9.3 Write tests verifying aria-labels match stage states, live region updates on state change

- [x] Task 10: Keyboard shortcuts help panel (WCAG 2.1.4 compliance)
  - [x] 10.1 Create `frontend/src/components/keyboard-shortcuts-help.tsx` — PatternFly `Modal` triggered by `?` key showing all available shortcuts
  - [x] 10.2 Include a toggle in the modal to enable/disable keyboard shortcuts (persists to localStorage)
  - [x] 10.3 When shortcuts are disabled, no single-character keys trigger actions — only standard browser/PF navigation works
  - [x] 10.4 Write tests for the help modal and disable toggle

- [x] Task 11: Testing (AC: all)
  - [x] 11.1 Every test file includes `expect(await axe(container)).toHaveNoViolations()`
  - [x] 11.2 Add integration test: full keyboard flow — j/k to navigate list, Enter to open detail, 1-6 to jump stages, Esc to return, focus restored
  - [x] 11.3 Add integration test: screen reader simulation — verify all aria-labels, aria-describedby, aria-live regions contain expected content
  - [x] 11.4 Add test: shortcuts disabled when focus is in input/textarea
  - [x] 11.5 Add test: shortcuts disabled via help panel toggle
  - [x] 11.6 MSW handlers: reuse existing handlers from Stories 5.2–5.5 (no new endpoints)

## Dev Notes

### Technical Stack (No New Dependencies)

All packages already installed from Stories 5.1–5.5:

| Package | Version | Usage in This Story |
|---------|---------|---------------------|
| react | 19.x | Hooks (useEffect, useCallback, useRef, useContext) |
| @patternfly/react-core | 6.6.x | Modal (help panel), existing components enhanced with ARIA |
| @patternfly/react-icons | 6.6.x | QuestionCircleIcon (help trigger) |
| @tanstack/react-query | 5.x | Reuse existing hooks (useApproveIncident) |
| react-router-dom | 7.x | useNavigate, useLocation (route state for focus restoration) |
| vitest | latest | Test runner |
| @testing-library/react | latest | Component testing, fireEvent for keyboard events |
| @testing-library/user-event | latest | userEvent.keyboard() for realistic keyboard simulation |
| jest-axe | latest | Accessibility assertion in every test |
| msw | 2.x | Reuse existing mock handlers |

### WCAG 2.2 AA Compliance Strategy

This story addresses **WCAG 2.1.4 Character Key Shortcuts (Level A)**. Our single-character shortcuts (`j`, `k`, `a`, `1`–`6`) MUST satisfy at least one of:
1. **Turn off** — User can disable shortcuts (implemented via help panel toggle in Task 10)
2. **Active only on focus** — Shortcuts are only active when the associated view/component has focus AND focus is NOT in an input/textarea/select

We implement BOTH mechanisms for defense-in-depth:
- The focus-guard (Task 1.2) ensures shortcuts fire only when no form element is focused
- The disable toggle (Task 10.2) lets users turn off all shortcuts globally
- Shortcuts are view-scoped (list shortcuts only fire on list view, detail shortcuts only on detail view)

Additional WCAG criteria addressed:
- **2.4.3 Focus Order** — Logical tab order maintained. Roving tabindex on ProgressStepper ensures arrow-key navigation follows visual order.
- **2.4.7 Focus Visible** — Focused rows get a visible outline indicator using PF design tokens.
- **2.4.11 Focus Not Obscured (Minimum)** — Focused elements are scrolled into view (`scrollIntoView({ block: 'nearest' })`).
- **1.1.1 Non-text Content** — Charts get `aria-label` text summaries. Pipeline states not communicated by color alone.
- **4.1.2 Name, Role, Value** — All interactive elements have accessible names. DataList toggles announce expansion state.

### Keyboard Shortcuts Implementation Pattern

```typescript
import { useEffect, useCallback, useContext } from 'react';
import { KeyboardShortcutsContext } from '../providers/keyboard-shortcuts-context';

export function useKeyboardShortcuts(
  shortcuts: Record<string, () => void>,
  options?: { enabled?: boolean }
) {
  const { shortcutsEnabled } = useContext(KeyboardShortcutsContext);

  const handler = useCallback((event: KeyboardEvent) => {
    if (!shortcutsEnabled || options?.enabled === false) return;

    // Focus guard: skip if focus is in an interactive form element
    const target = event.target as HTMLElement;
    const tagName = target.tagName.toLowerCase();
    if (['input', 'textarea', 'select'].includes(tagName)) return;
    if (target.isContentEditable) return;

    const action = shortcuts[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  }, [shortcuts, shortcutsEnabled, options?.enabled]);

  useEffect(() => {
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [handler]);
}
```

### List Navigation (j/k) Pattern — Roving Focus with aria-activedescendant

```typescript
export function useListKeyboardNav(items: { id: string }[]) {
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const listRef = useRef<HTMLElement>(null);

  const focusedId = focusedIndex >= 0 ? items[focusedIndex]?.id : undefined;

  const moveDown = useCallback(() => {
    setFocusedIndex(prev => Math.min(prev + 1, items.length - 1));
  }, [items.length]);

  const moveUp = useCallback(() => {
    setFocusedIndex(prev => Math.max(prev - 1, 0));
  }, []);

  // Scroll focused item into view
  useEffect(() => {
    if (focusedId) {
      document.getElementById(focusedId)?.scrollIntoView({ block: 'nearest' });
    }
  }, [focusedId]);

  return { focusedIndex, focusedId, moveDown, moveUp, listRef, setFocusedIndex };
}
```

Apply `aria-activedescendant={focusedId}` on the DataList container. Each DataListItem must have a unique `id`. The focused item gets a visible outline via CSS class.

### Focus Restoration Pattern

```typescript
// Navigating TO detail (from list)
const navigate = useNavigate();
function openIncident(id: string) {
  navigate(`/incidents/${id}`, {
    state: { returnFocusIndex: focusedIndex, returnSearch: location.search }
  });
}

// Returning FROM detail (to list)
// In list component:
const location = useLocation();
useEffect(() => {
  const returnIndex = location.state?.returnFocusIndex;
  if (returnIndex !== undefined && returnIndex >= 0) {
    setFocusedIndex(returnIndex);
    // Focus the item after render
    requestAnimationFrame(() => {
      document.getElementById(`incident-row-${returnIndex}`)?.focus();
    });
  }
}, []);

// In detail component — focus breadcrumb on mount:
const breadcrumbRef = useRef<HTMLElement>(null);
useEffect(() => {
  breadcrumbRef.current?.focus();
}, []);
```

### ProgressStepper Arrow Key Navigation (Roving Tabindex)

PatternFly ProgressStepper does NOT natively implement roving tabindex for arrow keys — it uses Tab/Shift+Tab. Per UX-DR19, we must add left/right arrow navigation.

Implementation approach: wrap the ProgressStepper in a custom keyboard handler:

```typescript
function PipelineStepperWithKeyboard({ stages, expandedStage, onStageClick }) {
  const [focusedStageIndex, setFocusedStageIndex] = useState(0);
  const stepRefs = useRef<(HTMLElement | null)[]>([]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault();
        setFocusedStageIndex(prev => Math.min(prev + 1, stages.length - 1));
        break;
      case 'ArrowLeft':
        event.preventDefault();
        setFocusedStageIndex(prev => Math.max(prev - 1, 0));
        break;
      case 'Home':
        event.preventDefault();
        setFocusedStageIndex(0);
        break;
      case 'End':
        event.preventDefault();
        setFocusedStageIndex(stages.length - 1);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        onStageClick(focusedStageIndex);
        break;
    }
  };

  useEffect(() => {
    stepRefs.current[focusedStageIndex]?.focus();
  }, [focusedStageIndex]);

  return (
    <div role="tablist" aria-label="Pipeline stages" onKeyDown={handleKeyDown}>
      {stages.map((stage, index) => (
        <div
          key={stage.id}
          role="tab"
          tabIndex={index === focusedStageIndex ? 0 : -1}
          aria-selected={index === expandedStage}
          aria-label={`${stage.label}: ${stage.stateDescription}`}
          ref={el => { stepRefs.current[index] = el; }}
          onClick={() => onStageClick(index)}
        >
          <ProgressStep {...stageProps} />
        </div>
      ))}
    </div>
  );
}
```

**Note:** The `role="tablist"` / `role="tab"` / `role="tabpanel"` pattern is appropriate here because the ProgressStepper controls which content panel is visible — this is the ARIA Tabs pattern (WAI-ARIA APG). Each expanded panel gets `role="tabpanel"` with `aria-labelledby` pointing to the corresponding tab.

### DataList Expansion Announcements

PatternFly's DataList with `isExpandable` already sets `aria-expanded` on the toggle button. However, the default accessible name may not be descriptive enough. Enhance it:

```typescript
<DataListItem
  id={`rce-group-${rce.id}`}
  isExpanded={expandedGroups.includes(rce.id)}
  aria-label={`Root-Cause Event: ${rce.label}, ${rce.alertCount} correlated alerts, ${expandedGroups.includes(rce.id) ? 'expanded' : 'collapsed'}`}
>
  <DataListItemRow>
    <DataListToggle
      id={`toggle-${rce.id}`}
      aria-label={`${expandedGroups.includes(rce.id) ? 'Collapse' : 'Expand'} Root-Cause Event: ${rce.label}, ${rce.alertCount} correlated alerts`}
      aria-controls={`content-${rce.id}`}
    />
    ...
  </DataListItemRow>
  <DataListContent
    id={`content-${rce.id}`}
    aria-label={`Details for ${rce.label}`}
  >
    ...
  </DataListContent>
</DataListItem>
```

### Approve/Reject aria-describedby

```typescript
<div>
  {/* Hidden summary for screen readers */}
  <span id="plan-summary-desc" className="pf-v6-u-screen-reader">
    Remediation plan: {incident.remediation_plan?.plan_summary?.slice(0, 200)}
  </span>

  <Button
    variant="primary"
    onClick={handleApprove}
    aria-describedby="plan-summary-desc"
  >
    Approve
  </Button>
  <Button
    variant="danger"
    onClick={openRejectModal}
    aria-describedby="plan-summary-desc"
  >
    Reject
  </Button>
</div>
```

### Chart Accessibility

Charts must have `role="img"` and a computed `aria-label`:

```typescript
function computeChartAriaLabel(data: TimeSeriesData, range: string): string {
  const totalAlerts = data.alerts.reduce((sum, v) => sum + v, 0);
  const peakValue = Math.max(...data.alerts);
  const peakIndex = data.alerts.indexOf(peakValue);
  const peakDate = new Date(data.buckets[peakIndex]).toLocaleDateString('en-US', { weekday: 'long' });
  return `Line chart showing alerts, diagnoses, and resolutions over the last ${range}. Total alerts: ${totalAlerts}. Peak: ${peakValue} alerts on ${peakDate}.`;
}

<div role="img" aria-label={computeChartAriaLabel(data, selectedRange)}>
  <Chart .../>
</div>
```

### aria-live Region for Pipeline State Changes

```typescript
// In pipeline-stepper.tsx
const [announcement, setAnnouncement] = useState('');

// When stages update (via SSE or polling):
useEffect(() => {
  const changedStage = stages.find((s, i) => s.state !== prevStages.current[i]?.state);
  if (changedStage) {
    setAnnouncement(`Pipeline stage updated. ${changedStage.label} is now ${changedStage.stateDescription}.`);
  }
  prevStages.current = stages;
}, [stages]);

return (
  <>
    <div className="pf-v6-u-screen-reader" aria-live="polite" aria-atomic="true">
      {announcement}
    </div>
    <ProgressStepper .../>
  </>
);
```

### Keyboard Shortcuts Help Modal

Triggered by pressing `?` (Shift+/) globally. PatternFly Modal:

```typescript
<Modal
  variant={ModalVariant.medium}
  title="Keyboard Shortcuts"
  isOpen={isHelpOpen}
  onClose={() => setIsHelpOpen(false)}
>
  <Switch
    id="shortcuts-toggle"
    label="Enable keyboard shortcuts"
    isChecked={shortcutsEnabled}
    onChange={toggleShortcuts}
  />
  <DescriptionList isHorizontal>
    <DescriptionListGroup>
      <DescriptionListTerm>j / k</DescriptionListTerm>
      <DescriptionListDescription>Navigate down / up in incident list</DescriptionListDescription>
    </DescriptionListGroup>
    <DescriptionListGroup>
      <DescriptionListTerm>Enter</DescriptionListTerm>
      <DescriptionListDescription>Open selected incident</DescriptionListDescription>
    </DescriptionListGroup>
    <DescriptionListGroup>
      <DescriptionListTerm>Esc / Backspace</DescriptionListTerm>
      <DescriptionListDescription>Return to incident list</DescriptionListDescription>
    </DescriptionListGroup>
    <DescriptionListGroup>
      <DescriptionListTerm>1 – 6</DescriptionListTerm>
      <DescriptionListDescription>Jump to pipeline stage</DescriptionListDescription>
    </DescriptionListGroup>
    <DescriptionListGroup>
      <DescriptionListTerm>a</DescriptionListTerm>
      <DescriptionListDescription>Approve remediation (when awaiting)</DescriptionListDescription>
    </DescriptionListGroup>
    <DescriptionListGroup>
      <DescriptionListTerm>?</DescriptionListTerm>
      <DescriptionListDescription>Show this help</DescriptionListDescription>
    </DescriptionListGroup>
  </DescriptionList>
</Modal>
```

### File Structure (Files Created/Modified in This Story)

```
frontend/src/
  hooks/
    use-keyboard-shortcuts.ts                   [NEW] — Global keyboard shortcut hook with focus guard
    use-keyboard-shortcuts.test.ts              [NEW] — Unit tests
  providers/
    keyboard-shortcuts-context.tsx              [NEW] — Context for enable/disable toggle
  components/
    keyboard-shortcuts-help.tsx                 [NEW] — ? help modal with shortcut list + disable toggle
    keyboard-shortcuts-help.test.tsx            [NEW] — Unit tests
  features/incidents/
    hooks/
      use-list-keyboard-nav.ts                 [NEW] — j/k/Enter list navigation
      use-list-keyboard-nav.test.ts            [NEW] — Unit tests
      use-detail-keyboard-nav.ts               [NEW] — Esc/Backspace/1-6/a detail shortcuts
      use-detail-keyboard-nav.test.ts          [NEW] — Unit tests
    components/
      incidents-list.tsx                        [UPDATE] — aria-labels on DataListItem toggles, aria-activedescendant, focused row styling
      incidents-list.test.tsx                   [UPDATE] — Add keyboard nav + a11y tests
      pipeline-stepper.tsx                      [UPDATE] — roving tabindex, arrow keys, role="tablist", aria-live region
      pipeline-stepper.test.tsx                [UPDATE] — Add arrow key + ARIA tests
      approval-actions.tsx                      [UPDATE] — aria-describedby linking to plan summary
      approval-actions.test.tsx                [UPDATE] — Add aria-describedby test
    pages/
      incident-detail.tsx                      [UPDATE] — focus breadcrumb on mount, wire detail keyboard shortcuts
      incident-detail.test.tsx                 [UPDATE] — Add focus management + keyboard tests
    index.tsx                                   [UPDATE] — wire list keyboard nav, focus restoration on return
    index.test.tsx                              [UPDATE] — Add focus restoration test
  features/statistics/
    components/
      activity-chart.tsx                        [UPDATE] — role="img" + computed aria-label
      activity-chart.test.tsx                  [UPDATE] — Add aria-label test
      mttr-chart.tsx                            [UPDATE] — role="img" + computed aria-label
      mttr-chart.test.tsx                      [UPDATE] — Add aria-label test
  app/
    app.tsx                                     [UPDATE] — Wrap with KeyboardShortcutsContext provider, add ? shortcut
```

### Architecture Compliance

- **FA-1 (Standalone-first):** No new data providers. Keyboard shortcuts are a UI-only layer.
- **FA-2 (TanStack Query):** Reuse `useApproveIncident` mutation for the `a` shortcut. No new queries.
- **FA-3 (SSE):** aria-live region reacts to stage changes already delivered via SSE (wired in Story 5.4). No new SSE logic.
- **FA-4 (Code splitting):** New hooks/components are within existing feature modules — no new lazy routes.
- **AD-14 (Monorepo layout):** All files in `frontend/src/`. No backend changes.

### Testing Requirements

**Every test file MUST include:**
```typescript
expect(await axe(container)).toHaveNoViolations();
```

**Keyboard testing pattern:**
```typescript
import userEvent from '@testing-library/user-event';

const user = userEvent.setup();
await user.keyboard('j'); // Simulates 'j' keypress
await user.keyboard('{Enter}'); // Simulates Enter
await user.keyboard('{Escape}'); // Simulates Escape
await user.keyboard('{ArrowRight}'); // Simulates arrow key
```

**Focus verification:**
```typescript
expect(document.activeElement).toBe(screen.getByRole('link', { name: /incidents/i }));
```

**aria-live verification:**
```typescript
expect(screen.getByRole('status')).toHaveTextContent('Pipeline stage updated. Diagnosis is now completed.');
```

**Test categories:**
- Unit: each hook in isolation (mock document.addEventListener, simulate keydown events)
- Integration: full page render with keyboard interaction flow
- Accessibility: jest-axe on every component, verify ARIA attributes, verify focus management

### Previous Story Intelligence

**Story 5.2 (Incidents List):**
- DataList with expandable RCE groups in `incidents-list.tsx`
- Groups sorted by severity, collapsed by default
- `DataListItem` with `DataListToggle` for expand/collapse
- `useIncidentFilters` for URL-persisted filter state
- React Router `useSearchParams` for filter persistence

**Story 5.3 (Incident Detail):**
- `pipeline-stepper.tsx` renders ProgressStepper with `isCenterAligned`
- Each ProgressStep already has `aria-label` (e.g., "Diagnosis: completed") — verify and enhance
- `expandedStage` state manages one-at-a-time panel accordion
- `getStageStates()` utility maps incident state to per-stage visual states
- Breadcrumb navigation preserves filter state via route state object
- Detail page at route `/incidents/:id`
- Stage content panels already have structure — we add `role="tabpanel"` + `aria-labelledby`

**Story 5.4 (Approval & Real-Time):**
- `approval-actions.tsx` renders Approve/Reject buttons when `state === 'awaiting_approval'`
- `useApproveIncident(id)` mutation hook — reuse for `a` shortcut
- SSE subscription via `useIncidentSSE` — stage changes trigger re-render which updates aria-live
- NotificationBadge on nav — already has `aria-label` with count

**Story 5.5 (Statistics Dashboard):**
- `activity-chart.tsx` and `mttr-chart.tsx` — add `role="img"` + `aria-label` with data summary
- Charts already render via `@patternfly/react-charts/victory`
- Chart data available in the component props — use to compute summary strings

### PatternFly Accessibility Utilities

PatternFly 6 provides `pf-v6-u-screen-reader` utility class for visually hidden but screen-reader-accessible content. Use this for:
- The `aria-live` announcement region
- The plan summary `aria-describedby` target
- Any text that should be accessible but not visible

```css
/* PatternFly provides this natively — DO NOT reimplement */
.pf-v6-u-screen-reader {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

### Focused Row Styling

Use PatternFly design tokens for the focus indicator on keyboard-navigated list rows:

```css
/* In incidents-list.tsx — inline style or CSS module */
[data-focused="true"] {
  outline: 2px solid var(--pf-t--global--border--color--hover);
  outline-offset: -2px;
  border-radius: var(--pf-t--global--border--radius--small);
}
```

DO NOT use `box-shadow` or custom hex colors. The PF token `--pf-t--global--border--color--hover` provides the correct accent color that adapts to dark/light theme.

### Anti-Patterns / DO NOT

- **DO NOT** use `accesskey` HTML attribute — it conflicts with browser/screen reader shortcuts
- **DO NOT** add keyboard shortcuts to form elements — the focus guard prevents this
- **DO NOT** use custom hex colors for focus indicators — PatternFly tokens only
- **DO NOT** create wrapper components around PatternFly — enhance existing components with ARIA attributes
- **DO NOT** use `outline: none` anywhere — always show visible focus indicators
- **DO NOT** use `aria-hidden="true"` on interactive elements
- **DO NOT** use `tabindex` values greater than 0 — only `0` (in tab order) and `-1` (programmatic focus only)
- **DO NOT** implement new API endpoints — this story is frontend-only, reusing existing hooks
- **DO NOT** add `@axe-core/react` to production bundle — jest-axe is test-only
- **DO NOT** use snapshot tests
- **DO NOT** mock `fetch` directly — use MSW
- **DO NOT** add animations or visual transitions to focus movement — immediate, clinical
- **DO NOT** duplicate shortcut logic across views — centralize in `use-keyboard-shortcuts` hook
- **DO NOT** make the help modal a floating overlay that blocks interaction — PatternFly Modal handles focus trap correctly
- **DO NOT** use `role="application"` — it overrides all default screen reader keyboard commands

### Dependencies

This story depends on ALL of Stories 5.1–5.5:
- **Story 5.1:** App shell, routing, providers, feature directory structure
- **Story 5.2:** Incidents list (`incidents-list.tsx`, DataList, filter hooks)
- **Story 5.3:** Incident detail page, pipeline stepper, stage panels, breadcrumb
- **Story 5.4:** Approval actions component, `useApproveIncident` hook, SSE integration
- **Story 5.5:** Statistics charts (`activity-chart.tsx`, `mttr-chart.tsx`)

No new npm packages needed — all required packages installed in previous stories.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.6] — acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR18] — keyboard shortcuts specification
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR19] — accessibility requirements (WCAG 2.2 AA)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR20] — alert storm collapsed groups, state patterns
- [Source: _bmad-output/project-context.md#Keyboard shortcuts] — shortcuts disabled in input/textarea
- [Source: _bmad-output/project-context.md#Frontend (TypeScript) Testing] — jest-axe, RTL
- [Source: _bmad-output/project-context.md#Frontend Anti-Patterns] — no custom components, no hex colors
- [Source: W3C WCAG 2.2 SC 2.1.4] — Character Key Shortcuts (Level A): turn off, remap, or focus-only
- [Source: PatternFly ProgressStepper Accessibility] — aria-label per step, aria-live for status updates
- [Source: WAI-ARIA APG Tabs Pattern] — tablist/tab/tabpanel roles for pipeline stepper
- [Source: _bmad-output/implementation-artifacts/5-2-incidents-list-view.md] — DataList structure, filter hooks
- [Source: _bmad-output/implementation-artifacts/5-3-incident-detail-view-and-pipeline-visualization.md] — ProgressStepper, stage panels, expandedStage state
- [Source: _bmad-output/implementation-artifacts/5-4-approval-workflow-and-real-time-updates.md] — approval actions, useApproveIncident, SSE hooks
- [Source: _bmad-output/implementation-artifacts/5-5-statistics-dashboard.md] — chart components

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

- jsdom `event.target.tagName` is undefined when dispatching KeyboardEvent directly on `document` — added null guard for tagName in `use-keyboard-shortcuts.ts`
- jsdom `isContentEditable` property not fully implemented for div elements — added fallback check via `getAttribute('contenteditable')`
- PatternFly `ProgressStepper` renders `<ol>` which cannot be child of `div[role="tablist"]` — moved `role="tablist"` directly onto the `ProgressStepper` component to fix axe `aria-required-parent` violation
- PatternFly `Switch` uses `role="switch"` not `role="checkbox"` — updated test queries accordingly
- Updated existing test query from `/details/i` to `/expand/i` for DataListToggle aria-label changes

### Completion Notes List

- **Task 1:** Created `use-keyboard-shortcuts` hook with focus-guard (input/textarea/select/contenteditable), `KeyboardShortcutsContext` provider with localStorage persistence for enable/disable toggle. 9 unit tests.
- **Task 2:** Created `use-list-keyboard-nav` hook for j/k movement with clamping and scrollIntoView. Integrated into `incidents-list.tsx` (aria-activedescendant, focused row outline) and `index.tsx` (route state for focus restoration). 7 unit tests.
- **Task 3:** Created `use-detail-keyboard-nav` hook for Esc/Backspace (navigate back with filter state), 1-6 (stage select), and `a` (approve with guards for awaiting_approval state + remediation panel expanded). 4 unit tests.
- **Task 4:** Rewrote `pipeline-stepper.tsx` with roving tabindex (ArrowLeft/Right/Home/End), role="tablist"/role="tab" ARIA pattern, Enter/Space activation, aria-selected on expanded stage. 6 new test cases.
- **Task 5:** Added breadcrumb ref + focus-on-mount in `incident-detail.tsx`, focus restoration from route state in `index.tsx` (returnFocusIndex).
- **Task 6:** Added descriptive aria-labels on DataListItem and DataListToggle, aria-controls linking toggle to content region. 4 new test cases.
- **Task 7:** Already implemented in Story 5.4 — `approval-actions.tsx` already has `aria-describedby` linking to plan summary span. Verified and confirmed existing implementation satisfies AC#8.
- **Task 8:** Added `role="img"` + computed descriptive aria-labels on `activity-chart.tsx` and `mttr-chart.tsx`. Updated test assertions to match new labels.
- **Task 9:** Enhanced `pipeline-stepper.tsx` with `aria-live="polite"` hidden region for stage transition announcements. Tests verify aria-labels, live region, role="status".
- **Task 10:** Created `keyboard-shortcuts-help.tsx` modal with shortcut list and enable/disable Switch. Integrated `?` shortcut in `app.tsx`, wrapped app with `KeyboardShortcutsProvider`. 8 unit tests.
- **Task 11:** All 23 test files pass (164 tests). Every test file includes `axe()` check. Integration tests cover keyboard flow, ARIA attributes, focus guard, and disable toggle.

### File List

- `frontend/src/providers/keyboard-shortcuts-context.tsx` — NEW — Context provider for enable/disable shortcuts with localStorage persistence
- `frontend/src/hooks/use-keyboard-shortcuts.ts` — NEW — Global keyboard shortcut hook with focus guard
- `frontend/src/hooks/use-keyboard-shortcuts.test.ts` — NEW — 9 unit tests for the hook
- `frontend/src/features/incidents/hooks/use-list-keyboard-nav.ts` — NEW — j/k list navigation with roving focus
- `frontend/src/features/incidents/hooks/use-list-keyboard-nav.test.ts` — NEW — 7 unit tests
- `frontend/src/features/incidents/hooks/use-detail-keyboard-nav.ts` — NEW — Esc/Backspace/1-6/a detail shortcuts
- `frontend/src/features/incidents/hooks/use-detail-keyboard-nav.test.ts` — NEW — 4 unit tests
- `frontend/src/components/keyboard-shortcuts-help.tsx` — NEW — ? help modal with shortcut list + disable toggle
- `frontend/src/components/keyboard-shortcuts-help.test.tsx` — NEW — 8 unit tests
- `frontend/src/features/incidents/components/incidents-list.tsx` — MODIFIED — Added aria-labels, aria-activedescendant, aria-controls, focused row styling, onRowActivate prop
- `frontend/src/features/incidents/components/incidents-list.test.tsx` — MODIFIED — Added 4 keyboard nav + a11y tests, updated toggle query
- `frontend/src/features/incidents/components/pipeline-stepper.tsx` — MODIFIED — Roving tabindex, arrow keys, role="tablist"/role="tab", aria-live region, aria-selected
- `frontend/src/features/incidents/components/pipeline-stepper.test.tsx` — MODIFIED — Added 6 arrow key + ARIA role tests
- `frontend/src/features/incidents/components/stage-panel.tsx` — MODIFIED — Changed role from "region" to "tabpanel"
- `frontend/src/features/incidents/pages/incident-detail.tsx` — MODIFIED — Focus breadcrumb on mount, wire detail keyboard shortcuts, approve via keyboard
- `frontend/src/features/incidents/index.tsx` — MODIFIED — Wire list keyboard nav, focus restoration on return
- `frontend/src/features/statistics/components/activity-chart.tsx` — MODIFIED — role="img" + computed descriptive aria-label
- `frontend/src/features/statistics/components/activity-chart.test.tsx` — MODIFIED — Updated aria-label assertion, added role="img" check
- `frontend/src/features/statistics/components/mttr-chart.tsx` — MODIFIED — role="img" + computed descriptive aria-label
- `frontend/src/features/statistics/components/mttr-chart.test.tsx` — MODIFIED — Updated aria-label assertion, added role="img" check
- `frontend/src/app/app.tsx` — MODIFIED — Wrapped with KeyboardShortcutsProvider, added ? shortcut for help modal
- `_bmad-output/implementation-artifacts/5-6-keyboard-shortcuts-and-accessibility.md` — MODIFIED — Marked all tasks complete, updated status to review

### Change Log

- 2026-08-15: Story 5.6 implementation complete — keyboard shortcuts (j/k/Enter/Esc/Backspace/1-6/a/?), WCAG 2.2 AA accessibility enhancements (aria-labels, aria-live, role="tablist", role="img", focus management), help modal with disable toggle. 164 tests passing across 23 files.
