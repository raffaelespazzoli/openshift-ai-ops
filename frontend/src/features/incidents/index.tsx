import { EmptyState, EmptyStateBody } from '@patternfly/react-core';
import { CubesIcon } from '@patternfly/react-icons';

export default function IncidentsPage() {
  return (
    <EmptyState headingLevel="h1" icon={CubesIcon} titleText="Incidents">
      <EmptyStateBody>Incident list view coming soon.</EmptyStateBody>
    </EmptyState>
  );
}
