import { useCallback, useState } from 'react';
import {
  Pagination,
  Select,
  SelectList,
  SelectOption,
  MenuToggle,
  MenuToggleElement,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core';
import type { IncidentFilters, IncidentSeverity } from '@models/incident';

interface IncidentsToolbarProps {
  filters: IncidentFilters;
  total: number;
  onFiltersChange: (updates: Partial<IncidentFilters>) => void;
}

const TIME_RANGE_OPTIONS = [
  { value: '1h', label: 'Last 1 hour' },
  { value: '6h', label: 'Last 6 hours' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
] as const;

const SEVERITY_OPTIONS: { value: IncidentSeverity; label: string }[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
];

export function IncidentsToolbar({ filters, total, onFiltersChange }: IncidentsToolbarProps) {
  const [isSeverityOpen, setIsSeverityOpen] = useState(false);
  const [isTimeRangeOpen, setIsTimeRangeOpen] = useState(false);

  const handleFiringSelect = useCallback(
    (_event: React.MouseEvent, isSelected: boolean) => {
      if (isSelected) onFiltersChange({ mode: 'firing', page: 1 });
    },
    [onFiltersChange],
  );

  const handleResolvedSelect = useCallback(
    (_event: React.MouseEvent, isSelected: boolean) => {
      if (isSelected) onFiltersChange({ mode: 'resolved', page: 1 });
    },
    [onFiltersChange],
  );

  const handleSeveritySelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      const sev = value as IncidentSeverity;
      const next = filters.severities.includes(sev)
        ? filters.severities.filter((s) => s !== sev)
        : [...filters.severities, sev];
      if (next.length > 0) {
        onFiltersChange({ severities: next, page: 1 });
      }
    },
    [filters.severities, onFiltersChange],
  );

  const handleTimeRangeSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      onFiltersChange({ timeRange: value as IncidentFilters['timeRange'], page: 1 });
      setIsTimeRangeOpen(false);
    },
    [onFiltersChange],
  );

  const handleSetPage = useCallback(
    (_event: React.MouseEvent | React.KeyboardEvent | MouseEvent, page: number) => {
      onFiltersChange({ page });
    },
    [onFiltersChange],
  );

  const handlePerPageSelect = useCallback(
    (_event: React.MouseEvent | React.KeyboardEvent | MouseEvent, perPage: number) => {
      onFiltersChange({ pageSize: perPage, page: 1 });
    },
    [onFiltersChange],
  );

  const severityLabel =
    filters.severities.length === 3
      ? 'All severities'
      : filters.severities.map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(', ') ||
        'Severity';

  const severityToggle = (toggleRef: React.Ref<MenuToggleElement>) => (
    <MenuToggle
      ref={toggleRef}
      onClick={() => setIsSeverityOpen((o) => !o)}
      isExpanded={isSeverityOpen}
    >
      {severityLabel}
    </MenuToggle>
  );

  const timeRangeLabel =
    TIME_RANGE_OPTIONS.find((o) => o.value === filters.timeRange)?.label ?? 'Time range';

  const timeRangeToggle = (toggleRef: React.Ref<MenuToggleElement>) => (
    <MenuToggle
      ref={toggleRef}
      onClick={() => setIsTimeRangeOpen((o) => !o)}
      isExpanded={isTimeRangeOpen}
    >
      {timeRangeLabel}
    </MenuToggle>
  );

  return (
    <Toolbar>
      <ToolbarContent>
        <ToolbarGroup>
          <ToolbarItem>
            <ToggleGroup aria-label="Incident mode filter">
              <ToggleGroupItem
                text="Firing"
                buttonId="firing"
                isSelected={filters.mode === 'firing'}
                onChange={handleFiringSelect}
              />
              <ToggleGroupItem
                text="Resolved"
                buttonId="resolved"
                isSelected={filters.mode === 'resolved'}
                onChange={handleResolvedSelect}
              />
            </ToggleGroup>
          </ToolbarItem>

          {filters.mode === 'resolved' && (
            <ToolbarItem>
              <Select
                aria-label="Time range filter"
                isOpen={isTimeRangeOpen}
                selected={filters.timeRange}
                onSelect={handleTimeRangeSelect}
                onOpenChange={setIsTimeRangeOpen}
                toggle={timeRangeToggle}
              >
                <SelectList>
                  {TIME_RANGE_OPTIONS.map((opt) => (
                    <SelectOption key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectOption>
                  ))}
                </SelectList>
              </Select>
            </ToolbarItem>
          )}

          <ToolbarItem>
            <Select
              aria-label="Severity filter"
              isOpen={isSeverityOpen}
              selected={filters.severities}
              onSelect={handleSeveritySelect}
              onOpenChange={setIsSeverityOpen}
              toggle={severityToggle}
            >
              <SelectList>
                {SEVERITY_OPTIONS.map((opt) => (
                  <SelectOption
                    key={opt.value}
                    value={opt.value}
                    hasCheckbox
                    isSelected={filters.severities.includes(opt.value)}
                  >
                    {opt.label}
                  </SelectOption>
                ))}
              </SelectList>
            </Select>
          </ToolbarItem>
        </ToolbarGroup>

        <ToolbarItem variant="pagination" align={{ default: 'alignEnd' }}>
          <Pagination
            itemCount={total}
            perPage={filters.pageSize}
            page={filters.page}
            onSetPage={handleSetPage}
            onPerPageSelect={handlePerPageSelect}
            isCompact
          />
        </ToolbarItem>
      </ToolbarContent>
    </Toolbar>
  );
}
