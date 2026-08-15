import {
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
} from '@patternfly/react-core';
import type { IncidentDetail } from '@models/incident';

interface TriagePanelProps {
  incident: IncidentDetail;
}

export function TriagePanel({ incident }: TriagePanelProps) {
  const { correlation_evidence, alerts } = incident;
  const alertSummary = alerts
    .map((a) => a.labels['alertname'] ?? a.fingerprint)
    .join(', ');

  return (
    <DescriptionList>
      <DescriptionListGroup>
        <DescriptionListTerm>Alert Payload</DescriptionListTerm>
        <DescriptionListDescription>
          {alertSummary || 'No alerts'}
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Correlation Reasoning</DescriptionListTerm>
        <DescriptionListDescription>
          {(correlation_evidence.reasoning as string) ?? 'N/A'}
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Priority Score</DescriptionListTerm>
        <DescriptionListDescription>
          {correlation_evidence.priority_score != null
            ? String(correlation_evidence.priority_score)
            : 'N/A'}
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  );
}
