import { Card, CardBody } from '@patternfly/react-core';
import type { ReactNode } from 'react';

interface StagePanelProps {
  stageId: string;
  stageLabel: string;
  isExpanded: boolean;
  children: ReactNode;
}

export function StagePanel({ stageId, stageLabel, isExpanded, children }: StagePanelProps) {
  if (!isExpanded) return null;

  return (
    <Card
      role="tabpanel"
      aria-labelledby={`stage-${stageId}-title`}
      aria-label={`${stageLabel} stage details`}
    >
      <CardBody>{children}</CardBody>
    </Card>
  );
}
