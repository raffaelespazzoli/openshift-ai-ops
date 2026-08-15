import { ToggleGroup, ToggleGroupItem } from '@patternfly/react-core';
import type { TimeRange } from '../hooks/use-statistics';

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}

const OPTIONS: { value: TimeRange; label: string }[] = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
];

export function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  return (
    <ToggleGroup aria-label="Time range selector">
      {OPTIONS.map((opt) => (
        <ToggleGroupItem
          key={opt.value}
          text={opt.label}
          buttonId={`time-range-${opt.value}`}
          isSelected={value === opt.value}
          onChange={() => onChange(opt.value)}
        />
      ))}
    </ToggleGroup>
  );
}
