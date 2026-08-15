import {
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
  Label,
} from '@patternfly/react-core';
import type { OutcomeData } from '@models/incident';

interface OutcomePanelProps {
  data: OutcomeData | null | undefined;
  isFailed?: boolean;
}

export function OutcomePanel({ data, isFailed }: OutcomePanelProps) {
  if (!data && !isFailed) {
    return <p>Outcome data not yet available.</p>;
  }

  if (!data && isFailed) {
    return (
      <DescriptionList>
        <DescriptionListGroup>
          <DescriptionListTerm>Resolution Status</DescriptionListTerm>
          <DescriptionListDescription>
            <Label isCompact color="red">Alert not resolved</Label>
          </DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    );
  }

  const ttr =
    data!.observation_started_at && data!.observation_completed_at
      ? `${Math.round(
          (new Date(data!.observation_completed_at).getTime() -
            new Date(data!.observation_started_at).getTime()) /
            1000,
        )}s`
      : 'N/A';

  return (
    <DescriptionList>
      <DescriptionListGroup>
        <DescriptionListTerm>Resolution Status</DescriptionListTerm>
        <DescriptionListDescription>
          <Label isCompact color={data!.alert_resolved ? 'green' : 'red'}>
            {data!.alert_resolved ? 'Alert resolved' : 'Alert not resolved'}
          </Label>
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Time to Resolution</DescriptionListTerm>
        <DescriptionListDescription>{ttr}</DescriptionListDescription>
      </DescriptionListGroup>
      {data!.resource_verification && (
        <DescriptionListGroup>
          <DescriptionListTerm>Verification</DescriptionListTerm>
          <DescriptionListDescription>
            {typeof data!.resource_verification === 'string'
              ? data!.resource_verification
              : JSON.stringify(data!.resource_verification, null, 2)}
          </DescriptionListDescription>
        </DescriptionListGroup>
      )}
      {data!.case_record_id && (
        <DescriptionListGroup>
          <DescriptionListTerm>Case Record</DescriptionListTerm>
          <DescriptionListDescription>{data!.case_record_id}</DescriptionListDescription>
        </DescriptionListGroup>
      )}
    </DescriptionList>
  );
}
