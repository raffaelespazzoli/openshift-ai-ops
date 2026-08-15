import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect } from 'vitest';
import { MttrChart } from './mttr-chart';
import { mockTimeseriesData, mockEmptyTimeseriesData } from '@mocks/handlers';
import type { TimeseriesData } from '../hooks/use-statistics';

expect.extend(toHaveNoViolations);

describe('MttrChart', () => {
  it('renders loading skeleton when isPending', () => {
    render(<MttrChart data={undefined} isPending={true} />);
    expect(screen.getByLabelText('MTTR chart loading')).toBeInTheDocument();
    expect(screen.getByText('Mean Time to Resolution')).toBeInTheDocument();
  });

  it('renders empty state when no data', () => {
    render(
      <MttrChart
        data={mockEmptyTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    expect(screen.getByText('No data for this time range.')).toBeInTheDocument();
  });

  it('renders chart with aria-label when data is present', () => {
    render(
      <MttrChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const chartContainer = screen.getByLabelText(/MTTR chart:/);
    expect(chartContainer).toBeInTheDocument();
  });

  it('renders the card title', () => {
    render(
      <MttrChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    expect(screen.getByText('Mean Time to Resolution')).toBeInTheDocument();
  });

  it('renders SVG elements for chart when data is present', () => {
    const { container } = render(
      <MttrChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBeGreaterThan(0);
  });

  it('has no accessibility violations in populated state', async () => {
    const { container } = render(
      <MttrChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has no accessibility violations in empty state', async () => {
    const { container } = render(
      <MttrChart
        data={mockEmptyTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
