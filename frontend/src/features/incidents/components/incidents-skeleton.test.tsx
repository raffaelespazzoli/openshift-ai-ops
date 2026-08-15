import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect } from 'vitest';
import { IncidentsSkeleton } from './incidents-skeleton';

expect.extend(toHaveNoViolations);

describe('IncidentsSkeleton', () => {
  it('renders skeleton rows', () => {
    render(<IncidentsSkeleton />);
    expect(screen.getByLabelText('Loading incidents')).toBeInTheDocument();
  });

  it('renders 8 skeleton rows', () => {
    const { container } = render(<IncidentsSkeleton />);
    const items = container.querySelectorAll('[id^="skeleton-"]');
    expect(items).toHaveLength(8);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<IncidentsSkeleton />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
