import {
  Alert as PfAlert,
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
  Label,
  List,
  ListItem,
} from '@patternfly/react-core';
import type { ExecutionData } from '@models/incident';

interface ExecutionPanelProps {
  data: ExecutionData | null | undefined;
  hasRollbackPlan?: boolean;
}

function statusColor(status: string): 'blue' | 'green' | 'red' {
  switch (status) {
    case 'running': return 'blue';
    case 'completed': return 'green';
    case 'failed': return 'red';
    default: return 'blue';
  }
}

function formatMcpCalls(calls: Record<string, unknown>[]): string {
  if (calls.length === 0) return 'None';
  return calls
    .map((c) => {
      if (typeof c === 'string') return c;
      return (c as Record<string, string>).tool ?? JSON.stringify(c);
    })
    .join(', ');
}

export function ExecutionPanel({ data, hasRollbackPlan }: ExecutionPanelProps) {
  if (!data) {
    return <p>Execution log not yet available.</p>;
  }

  const duration =
    data.started_at && data.completed_at
      ? `${Math.round((new Date(data.completed_at).getTime() - new Date(data.started_at).getTime()) / 1000)}s`
      : 'In progress';

  return (
    <div>
      {data.status === 'failed' && hasRollbackPlan && (
        <PfAlert variant="warning" isInline title="Rollback available" isPlain>
          A rollback plan is available for this failed remediation.
        </PfAlert>
      )}
      <DescriptionList>
        <DescriptionListGroup>
          <DescriptionListTerm>Status</DescriptionListTerm>
          <DescriptionListDescription>
            <Label isCompact color={statusColor(data.status)}>
              {data.status}
            </Label>
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Duration</DescriptionListTerm>
          <DescriptionListDescription>{duration}</DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Execution Log</DescriptionListTerm>
          <DescriptionListDescription>
            <List isPlain>
              {data.steps.map((step) => (
                <ListItem key={step.step_order}>
                  <strong>[{step.started_at}]</strong> {step.command}
                  {step.success ? ' ✓' : ' ✗'} — {step.output}
                </ListItem>
              ))}
            </List>
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>MCP Calls</DescriptionListTerm>
          <DescriptionListDescription>
            {formatMcpCalls(data.mcp_calls)}
          </DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    </div>
  );
}
