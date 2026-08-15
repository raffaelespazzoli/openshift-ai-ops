import {
  Card,
  CardBody,
  CardTitle,
  Grid,
  GridItem,
  Skeleton,
} from '@patternfly/react-core';
import {
  ArrowUpIcon,
  ArrowDownIcon,
  MinusIcon,
} from '@patternfly/react-icons';
import type { SummaryData, TrendDirection } from '../hooks/use-statistics';

interface SummaryCardsProps {
  data: SummaryData | undefined;
  isPending: boolean;
}

type TrendSemantics = 'positive' | 'negative' | 'neutral';

interface CardConfig {
  key: keyof SummaryData['trends'];
  title: string;
  format: (data: SummaryData) => string;
  upMeaning: TrendSemantics;
}

const CARD_CONFIGS: CardConfig[] = [
  {
    key: 'total_incidents',
    title: 'Total Incidents',
    format: (d) => String(d.total_incidents),
    upMeaning: 'neutral',
  },
  {
    key: 'auto_resolved_pct',
    title: 'Auto-Resolved',
    format: (d) => `${d.auto_resolved_pct}%`,
    upMeaning: 'positive',
  },
  {
    key: 'success_failure_ratio',
    title: 'Success/Failure',
    format: (d) => d.success_failure_ratio,
    upMeaning: 'positive',
  },
  {
    key: 'mttr_seconds',
    title: 'MTTR',
    format: (d) => formatMttr(d.mttr_seconds),
    upMeaning: 'negative',
  },
  {
    key: 'fast_path_hit_rate_pct',
    title: 'Fast-Path Rate',
    format: (d) => `${d.fast_path_hit_rate_pct}%`,
    upMeaning: 'positive',
  },
];

function formatMttr(seconds: number): string {
  if (seconds === 0) return '0s';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  if (s === 0) return `${m}m`;
  return `${m}m ${s}s`;
}

function getTrendColor(direction: TrendDirection, upMeaning: TrendSemantics): string {
  if (direction === 'flat') return 'var(--pf-t--global--color--status--info--default)';

  const isPositive =
    (direction === 'up' && upMeaning === 'positive') ||
    (direction === 'down' && upMeaning === 'negative');

  const isNegative =
    (direction === 'up' && upMeaning === 'negative') ||
    (direction === 'down' && upMeaning === 'positive');

  if (isPositive) return 'var(--pf-t--global--color--status--success--default)';
  if (isNegative) return 'var(--pf-t--global--color--status--danger--default)';
  return 'var(--pf-t--global--color--status--info--default)';
}

function TrendIndicator({
  direction,
  upMeaning,
}: {
  direction: TrendDirection;
  upMeaning: TrendSemantics;
}) {
  const color = getTrendColor(direction, upMeaning);
  const iconProps = { style: { color }, 'aria-hidden': true as const };

  const label =
    direction === 'up' ? 'Trending up' : direction === 'down' ? 'Trending down' : 'Flat trend';

  return (
    <span role="img" aria-label={label} style={{ marginLeft: '8px' }}>
      {direction === 'up' && <ArrowUpIcon {...iconProps} />}
      {direction === 'down' && <ArrowDownIcon {...iconProps} />}
      {direction === 'flat' && <MinusIcon {...iconProps} />}
    </span>
  );
}

function isNoData(data: SummaryData | undefined): boolean {
  if (!data) return true;
  return data.total_incidents === 0;
}

export function SummaryCards({ data, isPending }: SummaryCardsProps) {
  const isEmpty = !isPending && isNoData(data);

  return (
    <Grid hasGutter>
      {CARD_CONFIGS.map((config) => (
        <GridItem key={config.key} xl={2} lg={4} md={6} sm={12}>
          <Card isCompact>
            <CardTitle>{config.title}</CardTitle>
            <CardBody>
              {isPending ? (
                <span role="status" aria-label={`${config.title} loading`}>
                  <Skeleton width="80px" />
                </span>
              ) : (
                <span
                  style={{ fontSize: 'var(--pf-t--global--font--size--heading--h3)', fontWeight: 700 }}
                >
                  {isEmpty ? '\u2014' : config.format(data!)}
                  {!isEmpty && data && (
                    <TrendIndicator
                      direction={data.trends[config.key]}
                      upMeaning={config.upMeaning}
                    />
                  )}
                </span>
              )}
            </CardBody>
          </Card>
        </GridItem>
      ))}
    </Grid>
  );
}
