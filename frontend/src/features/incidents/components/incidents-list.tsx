import { useCallback, useState } from 'react';
import {
  Button,
  DataList,
  DataListItem,
  DataListItemRow,
  DataListItemCells,
  DataListCell,
  DataListToggle,
  DataListContent,
  Label,
} from '@patternfly/react-core';
import type { IncidentListItem, IncidentSeverity } from '@models/incident';
import { formatRelativeTime } from '@utils/date';

interface IncidentsListProps {
  items: IncidentListItem[];
  focusedIndex?: number;
  onRowActivate?: (id: string, index: number) => void;
}

const SEVERITY_VARIANT: Record<IncidentSeverity, 'red' | 'orange' | 'blue'> = {
  critical: 'red',
  warning: 'orange',
  info: 'blue',
};

function formatState(state: string): string {
  return state
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export function IncidentsList({ items, focusedIndex = -1, onRowActivate }: IncidentsListProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const handleToggle = useCallback((_event: React.MouseEvent, id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleRowClick = useCallback(
    (id: string, index: number) => {
      if (onRowActivate) {
        onRowActivate(id, index);
      }
    },
    [onRowActivate],
  );

  const focusedId = focusedIndex >= 0 ? items[focusedIndex]?.id : undefined;

  return (
    <DataList
      aria-label="Incidents list"
      aria-activedescendant={focusedId}
    >
      {items.map((item, index) => {
        const isExpanded = expanded.has(item.id);
        const isFocused = focusedIndex === index;
        return (
          <DataListItem
            key={item.id}
            id={item.id}
            isExpanded={isExpanded}
            aria-label={`Root-Cause Event: ${formatState(item.state)}, severity ${item.severity}, ${isExpanded ? 'expanded' : 'collapsed'}`}
            style={
              isFocused
                ? {
                    outline: '2px solid var(--pf-t--global--border--color--hover)',
                    outlineOffset: '-2px',
                    borderRadius: 'var(--pf-t--global--border--radius--small)',
                  }
                : undefined
            }
          >
            <DataListItemRow>
              <DataListToggle
                id={`toggle-${item.id}`}
                onClick={(e) => handleToggle(e, item.id)}
                isExpanded={isExpanded}
                aria-label={`${isExpanded ? 'Collapse' : 'Expand'} incident ${formatState(item.state)}, severity ${item.severity}`}
                aria-controls={`content-${item.id}`}
              />
              <DataListItemCells
                dataListCells={[
                  <DataListCell key="severity" width={1}>
                    <Label color={SEVERITY_VARIANT[item.severity]}>{item.severity}</Label>
                  </DataListCell>,
                  <DataListCell key="state" width={2}>
                    <Button variant="link" isInline onClick={() => handleRowClick(item.id, index)}>
                      {formatState(item.state)}
                    </Button>
                  </DataListCell>,
                  <DataListCell key="time" width={2}>
                    {formatRelativeTime(item.created_at)}
                  </DataListCell>,
                  <DataListCell key="fast-path" width={1}>
                    {item.fast_path && <Label color="blue" isCompact>Fast-Path</Label>}
                  </DataListCell>,
                ]}
              />
            </DataListItemRow>
            <DataListContent
              aria-label={`Details for incident ${item.id}`}
              id={`content-${item.id}`}
              isHidden={!isExpanded}
            >
              <p>
                <strong>Incident ID:</strong> {item.id}
              </p>
              <p>
                <strong>Last updated:</strong> {formatRelativeTime(item.updated_at)}
              </p>
            </DataListContent>
          </DataListItem>
        );
      })}
    </DataList>
  );
}
