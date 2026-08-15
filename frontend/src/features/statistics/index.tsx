import { EmptyState, EmptyStateBody } from '@patternfly/react-core';
import { CubesIcon } from '@patternfly/react-icons';

export default function StatisticsPage() {
  return (
    <EmptyState headingLevel="h1" icon={CubesIcon} titleText="Statistics">
      <EmptyStateBody>Statistics dashboard coming soon.</EmptyStateBody>
    </EmptyState>
  );
}
