import {
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
  Label,
} from '@patternfly/react-core';
import type { SkepticData } from '@models/incident';

interface SkepticPanelProps {
  data: SkepticData | null | undefined;
}

export function SkepticPanel({ data }: SkepticPanelProps) {
  if (!data) {
    return <p>Skeptic review not yet available.</p>;
  }

  return (
    <DescriptionList>
      <DescriptionListGroup>
        <DescriptionListTerm>Challenge</DescriptionListTerm>
        <DescriptionListDescription>{data.challenge}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Response</DescriptionListTerm>
        <DescriptionListDescription>{data.response}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Verdict</DescriptionListTerm>
        <DescriptionListDescription>
          <Label isCompact color={data.verdict === 'pass' ? 'green' : 'red'}>
            {data.verdict === 'pass' ? 'Pass' : 'Fail'}
          </Label>
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  );
}
