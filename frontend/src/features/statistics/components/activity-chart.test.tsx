import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect } from 'vitest';
import { ActivityChart } from './activity-chart';
import { mockTimeseriesData, mockEmptyTimeseriesData } from '@mocks/handlers';
import type { TimeseriesData } from '../hooks/use-statistics';

expect.extend(toHaveNoViolations);

describe('ActivityChart', () => {
  it('renders loading skeleton when isPending', () => {
    render(<ActivityChart data={undefined} isPending={true} />);
    expect(screen.getByLabelText('Activity chart loading')).toBeInTheDocument();
    expect(screen.getByText('Activity Over Time')).toBeInTheDocument();
  });

  it('renders empty state when no data', () => {
    render(
      <ActivityChart
        data={mockEmptyTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    expect(screen.getByText('No data for this time range.')).toBeInTheDocument();
  });

  it('renders chart with aria-label when data is present', () => {
    render(
      <ActivityChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const chartContainer = screen.getByLabelText(/Line chart showing alerts/);
    expect(chartContainer).toBeInTheDocument();
    expect(chartContainer).toHaveAttribute('role', 'img');
  });

  it('renders the card title', () => {
    render(
      <ActivityChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    expect(screen.getByText('Activity Over Time')).toBeInTheDocument();
  });

  it('renders SVG elements for chart when data is present', () => {
    const { container } = render(
      <ActivityChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const svgs = container.querySelectorAll('svg');
    expect(svgs.length).toBeGreaterThan(0);
  });

  it('has no accessibility violations in populated state', async () => {
    const { container } = render(
      <ActivityChart
        data={mockTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has no accessibility violations in empty state', async () => {
    const { container } = render(
      <ActivityChart
        data={mockEmptyTimeseriesData as TimeseriesData}
        isPending={false}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
