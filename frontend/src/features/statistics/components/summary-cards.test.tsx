import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect } from 'vitest';
import { SummaryCards } from './summary-cards';
import { mockSummaryData, mockEmptySummaryData } from '@mocks/handlers';
import type { SummaryData } from '../hooks/use-statistics';

expect.extend(toHaveNoViolations);

describe('SummaryCards', () => {
  it('renders loading skeletons when isPending', () => {
    render(<SummaryCards data={undefined} isPending={true} />);
    expect(screen.getByLabelText('Total Incidents loading')).toBeInTheDocument();
    expect(screen.getByLabelText('Auto-Resolved loading')).toBeInTheDocument();
    expect(screen.getByLabelText('MTTR loading')).toBeInTheDocument();
  });

  it('renders populated values from data', () => {
    render(<SummaryCards data={mockSummaryData as SummaryData} isPending={false} />);
    expect(screen.getByText('142')).toBeInTheDocument();
    expect(screen.getByText('67.5%')).toBeInTheDocument();
    expect(screen.getByText('4.2:1')).toBeInTheDocument();
    expect(screen.getByText('23.8%')).toBeInTheDocument();
  });

  it('renders all five card titles', () => {
    render(<SummaryCards data={mockSummaryData as SummaryData} isPending={false} />);
    expect(screen.getByText('Total Incidents')).toBeInTheDocument();
    expect(screen.getByText('Auto-Resolved')).toBeInTheDocument();
    expect(screen.getByText('Success/Failure')).toBeInTheDocument();
    expect(screen.getByText('MTTR')).toBeInTheDocument();
    expect(screen.getByText('Fast-Path Rate')).toBeInTheDocument();
  });

  it('renders trend indicators with accessible labels', () => {
    render(<SummaryCards data={mockSummaryData as SummaryData} isPending={false} />);
    const upTrends = screen.getAllByLabelText('Trending up');
    const downTrends = screen.getAllByLabelText('Trending down');
    const flatTrends = screen.getAllByLabelText('Flat trend');
    expect(upTrends.length).toBeGreaterThan(0);
    expect(downTrends.length).toBeGreaterThan(0);
    expect(flatTrends.length).toBeGreaterThan(0);
  });

  it('renders dashes for empty state (no data)', () => {
    render(<SummaryCards data={undefined} isPending={false} />);
    const dashes = screen.getAllByText('\u2014');
    expect(dashes).toHaveLength(5);
  });

  it('renders dashes for zeroed summary data (fresh deployment)', () => {
    render(<SummaryCards data={mockEmptySummaryData as SummaryData} isPending={false} />);
    const dashes = screen.getAllByText('\u2014');
    expect(dashes).toHaveLength(5);
  });

  it('has no accessibility violations in populated state', async () => {
    const { container } = render(
      <SummaryCards data={mockSummaryData as SummaryData} isPending={false} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has no accessibility violations in loading state', async () => {
    const { container } = render(
      <SummaryCards data={undefined} isPending={true} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
