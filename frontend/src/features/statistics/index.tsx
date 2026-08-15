import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  PageSection,
  Title,
  Flex,
  FlexItem,
} from '@patternfly/react-core';
import { SummaryCards } from './components/summary-cards';
import { TimeRangeSelector } from './components/time-range-selector';
import { ActivityChart } from './components/activity-chart';
import { MttrChart } from './components/mttr-chart';
import {
  useStatisticsSummary,
  useStatisticsTimeseries,
} from './hooks/use-statistics';
import type { TimeRange } from './hooks/use-statistics';

const VALID_RANGES = new Set<TimeRange>(['day', 'week', 'month']);

function isValidRange(val: string | null): val is TimeRange {
  return val !== null && VALID_RANGES.has(val as TimeRange);
}

export default function StatisticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rangeParam = searchParams.get('range');
  const range: TimeRange = isValidRange(rangeParam) ? rangeParam : 'week';

  const handleRangeChange = useCallback(
    (newRange: TimeRange) => {
      setSearchParams({ range: newRange }, { replace: true });
    },
    [setSearchParams],
  );

  const summary = useStatisticsSummary(range);
  const timeseries = useStatisticsTimeseries(range);

  return (
    <>
      <PageSection>
        <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }} alignItems={{ default: 'alignItemsCenter' }}>
          <FlexItem>
            <Title headingLevel="h1">Statistics</Title>
          </FlexItem>
          <FlexItem>
            <TimeRangeSelector value={range} onChange={handleRangeChange} />
          </FlexItem>
        </Flex>
      </PageSection>

      <PageSection>
        <SummaryCards data={summary.data} isPending={summary.isPending} />
      </PageSection>

      <PageSection>
        <Flex direction={{ default: 'column' }} gap={{ default: 'gapLg' }}>
          <FlexItem>
            <ActivityChart data={timeseries.data} isPending={timeseries.isPending} />
          </FlexItem>
          <FlexItem>
            <MttrChart data={timeseries.data} isPending={timeseries.isPending} />
          </FlexItem>
        </Flex>
      </PageSection>
    </>
  );
}
