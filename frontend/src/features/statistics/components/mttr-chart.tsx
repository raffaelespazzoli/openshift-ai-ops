import {
  Chart,
  ChartArea,
  ChartAxis,
  ChartThemeColor,
  ChartVoronoiContainer,
} from '@patternfly/react-charts/victory';
import {
  Card,
  CardBody,
  CardTitle,
  EmptyState,
  EmptyStateBody,
  Skeleton,
} from '@patternfly/react-core';
import { CubesIcon } from '@patternfly/react-icons';
import type { TimeseriesData } from '../hooks/use-statistics';
import { useContainerWidth } from '@hooks/use-container-width';

interface MttrChartProps {
  data: TimeseriesData | undefined;
  isPending: boolean;
}

function formatBucketLabel(iso: string): string {
  const date = new Date(iso);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
  }).format(date);
}

function formatSeconds(seconds: number): string {
  if (seconds === 0) return '0s';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  if (s === 0) return `${m}m`;
  return `${m}m ${s}s`;
}

export function MttrChart({ data, isPending }: MttrChartProps) {
  const [containerRef, chartWidth] = useContainerWidth();

  if (isPending) {
    return (
      <Card>
        <CardTitle>Mean Time to Resolution</CardTitle>
        <CardBody>
          <Skeleton height="250px" width="100%" aria-label="MTTR chart loading" />
        </CardBody>
      </Card>
    );
  }

  const isEmpty = !data || data.buckets.length === 0 || data.mttr_seconds.every((v) => v === 0);

  if (isEmpty) {
    return (
      <Card>
        <CardTitle>Mean Time to Resolution</CardTitle>
        <CardBody>
          <EmptyState headingLevel="h4" icon={CubesIcon} titleText="No data">
            <EmptyStateBody>No data for this time range.</EmptyStateBody>
          </EmptyState>
        </CardBody>
      </Card>
    );
  }

  const chartData = data.buckets.map((b, i) => ({
    x: formatBucketLabel(b),
    y: data.mttr_seconds[i] ?? 0,
  }));

  const maxVal = Math.max(...data.mttr_seconds, 1);

  const tickCount = Math.min(data.buckets.length, 8);
  const step = Math.max(1, Math.floor(data.buckets.length / tickCount));
  const tickValues = data.buckets
    .filter((_, i) => i % step === 0)
    .map((b) => formatBucketLabel(b));

  const avgMttr = Math.round(
    data.mttr_seconds.reduce((a, b) => a + b, 0) / data.mttr_seconds.length,
  );

  return (
    <Card>
      <CardTitle>Mean Time to Resolution</CardTitle>
      <CardBody>
        <div
          ref={containerRef}
          aria-label={`MTTR chart: average ${formatSeconds(avgMttr)} over the selected period`}
        >
          <Chart
            ariaTitle="Mean time to resolution"
            containerComponent={
              <ChartVoronoiContainer
                labels={({ datum }: { datum: { x: string; y: number } }) =>
                  `${datum.x}: ${formatSeconds(datum.y)}`
                }
              />
            }
            domain={{ y: [0, maxVal + 60] }}
            height={250}
            width={chartWidth}
            padding={{ top: 20, right: 30, bottom: 50, left: 50 }}
            themeColor={ChartThemeColor.blue}
          >
            <ChartAxis tickValues={tickValues} fixLabelOverlap />
            <ChartAxis
              dependentAxis
              showGrid
              tickFormat={(t: number) => formatSeconds(t)}
            />
            <ChartArea
              data={chartData}
              interpolation="monotoneX"
              name="MTTR"
            />
          </Chart>
        </div>
      </CardBody>
    </Card>
  );
}
