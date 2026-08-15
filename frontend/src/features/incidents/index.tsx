import {
  Button,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  Title,
} from '@patternfly/react-core';
import { CheckCircleIcon, ExclamationCircleIcon } from '@patternfly/react-icons';
import { useIncidentFilters } from './hooks/use-incident-filters';
import { useIncidents } from './hooks/use-incidents';
import { IncidentsToolbar } from './components/incidents-toolbar';
import { IncidentsList } from './components/incidents-list';
import { IncidentsSkeleton } from './components/incidents-skeleton';

export default function IncidentsPage() {
  const { filters, setFilters } = useIncidentFilters();
  const { data, isPending, isError, refetch } = useIncidents(filters);

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
      <IncidentsList items={data.items} />
    </>
  );
}
