import {
  Chart,
  ChartAxis,
  ChartGroup,
  ChartLegend,
  ChartLine,
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

interface ActivityChartProps {
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

export function ActivityChart({ data, isPending }: ActivityChartProps) {
  const [containerRef, chartWidth] = useContainerWidth();

  if (isPending) {
    return (
      <Card>
        <CardTitle>Activity Over Time</CardTitle>
        <CardBody>
          <Skeleton height="250px" width="100%" aria-label="Activity chart loading" />
        </CardBody>
      </Card>
    );
  }

  const isEmpty = !data || data.buckets.length === 0 || data.alerts.every((v) => v === 0);

  if (isEmpty) {
    return (
      <Card>
        <CardTitle>Activity Over Time</CardTitle>
        <CardBody>
          <EmptyState headingLevel="h4" icon={CubesIcon} titleText="No data">
            <EmptyStateBody>No data for this time range.</EmptyStateBody>
          </EmptyState>
        </CardBody>
      </Card>
    );
  }

  const alertsData = data.buckets.map((b, i) => ({ x: formatBucketLabel(b), y: data.alerts[i] ?? 0 }));
  const diagnosesData = data.buckets.map((b, i) => ({ x: formatBucketLabel(b), y: data.diagnoses[i] ?? 0 }));
  const resolutionsData = data.buckets.map((b, i) => ({ x: formatBucketLabel(b), y: data.resolutions[i] ?? 0 }));

  const maxVal = Math.max(
    ...data.alerts,
    ...data.diagnoses,
    ...data.resolutions,
    1,
  );

  const tickCount = Math.min(data.buckets.length, 8);
  const step = Math.max(1, Math.floor(data.buckets.length / tickCount));
  const tickValues = data.buckets
    .filter((_, i) => i % step === 0)
    .map((b) => formatBucketLabel(b));

  return (
    <Card>
      <CardTitle>Activity Over Time</CardTitle>
      <CardBody>
        <div
          ref={containerRef}
          aria-label={`Activity chart: ${data.alerts.reduce((a, b) => a + b, 0)} alerts, ${data.diagnoses.reduce((a, b) => a + b, 0)} diagnoses, ${data.resolutions.reduce((a, b) => a + b, 0)} resolutions in selected period`}
        >
          <Chart
            ariaTitle="Activity over time"
            containerComponent={
              <ChartVoronoiContainer
                labels={({ datum }: { datum: { x: string; y: number } }) =>
                  `${datum.x}: ${datum.y}`
                }
              />
            }
            domain={{ y: [0, maxVal + 1] }}
            height={250}
            width={chartWidth}
            padding={{ top: 20, right: 30, bottom: 50, left: 50 }}
            themeColor={ChartThemeColor.multiOrdered}
          >
            <ChartAxis tickValues={tickValues} fixLabelOverlap />
            <ChartAxis dependentAxis showGrid />
            <ChartGroup>
              <ChartLine
                data={alertsData}
                interpolation="monotoneX"
                name="Alerts"
              />
              <ChartLine
                data={diagnosesData}
                interpolation="monotoneX"
                name="Diagnoses"
              />
              <ChartLine
                data={resolutionsData}
                interpolation="monotoneX"
                name="Resolutions"
              />
            </ChartGroup>
            <ChartLegend
              data={[
                { name: 'Alerts' },
                { name: 'Diagnoses' },
                { name: 'Resolutions' },
              ]}
            />
          </Chart>
        </div>
      </CardBody>
    </Card>
  );
}
