import {
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
  Label,
  List,
  ListItem,
  ExpandableSection,
} from '@patternfly/react-core';
import { useState } from 'react';
import { ConfidenceBadge } from '@components/confidence-badge';
import type { BlastRadius, IncidentState, RemediationData } from '@models/incident';
import { ApprovalActions } from './approval-actions';

interface RemediationPanelProps {
  data: RemediationData | null | undefined;
  incidentId?: string;
  incidentState?: IncidentState;
}

const BLAST_RADIUS_COLOR: Record<BlastRadius, 'blue' | 'orange' | 'red'> = {
  workload: 'blue',
  namespace: 'orange',
  node: 'red',
  cluster: 'red',
};

export function RemediationPanel({ data, incidentId, incidentState }: RemediationPanelProps) {
  const [rollbackExpanded, setRollbackExpanded] = useState(false);

  if (!data) {
    return <p>Remediation plan not yet available.</p>;
  }

  const showApprovalActions = incidentState === 'awaiting_approval' && incidentId;

  return (
    <div>
      {showApprovalActions && (
        <ApprovalActions incidentId={incidentId} planSummary={data.plan_summary} />
      )}
      <DescriptionList>
        <DescriptionListGroup>
          <DescriptionListTerm>Plan Summary</DescriptionListTerm>
          <DescriptionListDescription>{data.plan_summary}</DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Steps</DescriptionListTerm>
          <DescriptionListDescription>
            <List isPlain component="ol">
              {data.steps.map((step) => (
                <ListItem key={step.order}>
                  {step.description} ({step.action} {step.resource})
                </ListItem>
              ))}
            </List>
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Blast Radius</DescriptionListTerm>
          <DescriptionListDescription>
            <Label isCompact color={BLAST_RADIUS_COLOR[data.blast_radius]}>
              {data.blast_radius}
            </Label>
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Rollback Plan</DescriptionListTerm>
          <DescriptionListDescription>
            <ExpandableSection
              toggleText={rollbackExpanded ? 'Hide rollback plan' : 'Show rollback plan'}
              isExpanded={rollbackExpanded}
              onToggle={(_event, expanded) => setRollbackExpanded(expanded)}
            >
              <List isPlain component="ol">
                {data.rollback_plan.map((step) => (
                  <ListItem key={step.order}>
                    {step.description} ({step.action} {step.resource})
                  </ListItem>
                ))}
              </List>
            </ExpandableSection>
          </DescriptionListDescription>
        </DescriptionListGroup>
        {data.dry_run_confidence != null && (
          <DescriptionListGroup>
            <DescriptionListTerm>Dry-Run Confidence</DescriptionListTerm>
            <DescriptionListDescription>
              <ConfidenceBadge confidence={data.dry_run_confidence} />
            </DescriptionListDescription>
          </DescriptionListGroup>
        )}
        <DescriptionListGroup>
          <DescriptionListTerm>Preconditions</DescriptionListTerm>
          <DescriptionListDescription>
            <List isPlain>
              {data.preconditions.map((pre, i) => (
                <ListItem key={i}>
                  {pre.description} — {pre.satisfied ? '✓ Satisfied' : '✗ Not satisfied'}
                </ListItem>
              ))}
              {data.preconditions.length === 0 && <ListItem>No preconditions</ListItem>}
            </List>
          </DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    </div>
  );
}
