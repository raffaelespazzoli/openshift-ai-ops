import { useCallback, useEffect, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Button,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
} from '@patternfly/react-core';
import { CheckCircleIcon, ExclamationCircleIcon } from '@patternfly/react-icons';
import { useIncidentFilters } from './hooks/use-incident-filters';
import { useIncidents } from './hooks/use-incidents';
import { useListKeyboardNav } from './hooks/use-list-keyboard-nav';
import { useKeyboardShortcuts } from '@hooks/use-keyboard-shortcuts';
import { IncidentsToolbar } from './components/incidents-toolbar';
import { IncidentsList } from './components/incidents-list';
import { IncidentsSkeleton } from './components/incidents-skeleton';

export default function IncidentsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { filters, setFilters } = useIncidentFilters();
  const { data, isPending, isError, refetch } = useIncidents(filters);

  const items = useMemo(() => data?.items ?? [], [data]);
  const { focusedIndex, focusedId, moveDown, moveUp, setFocusedIndex } =
    useListKeyboardNav(items);

  useEffect(() => {
    const returnIndex = (location.state as { returnFocusIndex?: number } | null)?.returnFocusIndex;
    if (returnIndex !== undefined && returnIndex >= 0) {
      setFocusedIndex(returnIndex);
      requestAnimationFrame(() => {
        const id = items[returnIndex]?.id;
        if (id) document.getElementById(id)?.scrollIntoView({ block: 'nearest' });
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openFocused = useCallback(() => {
    if (focusedId) {
      navigate(`/incidents/${focusedId}`, {
        state: { returnFocusIndex: focusedIndex, returnSearch: location.search },
      });
    }
  }, [focusedId, focusedIndex, navigate, location.search]);

  const shortcuts = useMemo(
    () => ({
      j: moveDown,
      k: moveUp,
      Enter: openFocused,
    }),
    [moveDown, moveUp, openFocused],
  );

  useKeyboardShortcuts(shortcuts, { enabled: !isPending && !isError });

  const handleRowActivate = useCallback(
    (id: string, index: number) => {
      navigate(`/incidents/${id}`, {
        state: { returnFocusIndex: index, returnSearch: location.search },
      });
    },
    [navigate, location.search],
  );

  if (isPending) {
    return (
      <>
        <IncidentsToolbar filters={filters} total={0} onFiltersChange={setFilters} />
        <IncidentsSkeleton />
      </>
    );
  }

  if (isError) {
    return (
      <EmptyState headingLevel="h1" icon={ExclamationCircleIcon} titleText="Unable to reach the API.">
        <EmptyStateBody>
          An error occurred while loading incidents. Please check your connection and try again.
        </EmptyStateBody>
        <EmptyStateFooter>
          <EmptyStateActions>
            <Button variant="primary" onClick={() => refetch()}>
              Retry
            </Button>
          </EmptyStateActions>
        </EmptyStateFooter>
      </EmptyState>
    );
  }

  if (data.items.length === 0) {
    return (
      <>
        <IncidentsToolbar filters={filters} total={0} onFiltersChange={setFilters} />
        <EmptyState headingLevel="h1" icon={CheckCircleIcon} titleText="No active alerts.">
          <EmptyStateBody>
            {filters.mode === 'firing'
              ? 'There are no active incidents matching the current filters.'
              : 'There are no resolved incidents matching the current filters.'}
          </EmptyStateBody>
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <IncidentsToolbar filters={filters} total={data.total} onFiltersChange={setFilters} />
      <IncidentsList
        items={data.items}
        focusedIndex={focusedIndex}
        onRowActivate={handleRowActivate}
      />
    </>
  );
}
