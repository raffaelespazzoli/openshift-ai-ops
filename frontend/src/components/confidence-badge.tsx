import { Label } from '@patternfly/react-core';

interface ConfidenceBadgeProps {
  confidence: number;
}

function getConfidenceTier(confidence: number): 'green' | 'orange' | 'red' {
  if (confidence >= 0.8) return 'green';
  if (confidence >= 0.5) return 'orange';
  return 'red';
}

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const variant = getConfidenceTier(confidence);
  const text = `${Math.round(confidence * 100)}%`;

  return (
    <Label isCompact color={variant}>
      {text}
    </Label>
  );
}
