import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, vi } from 'vitest';
import type { IncidentFilters } from '@models/incident';
import { IncidentsToolbar } from './incidents-toolbar';

expect.extend(toHaveNoViolations);

function defaultFilters(overrides?: Partial<IncidentFilters>): IncidentFilters {
  return {
    mode: 'firing',
    severities: ['critical', 'warning', 'info'],
    page: 1,
    pageSize: 50,
    ...overrides,
  };
}

describe('IncidentsToolbar', () => {
  it('renders the Firing/Resolved toggle group', () => {
    render(
      <IncidentsToolbar
        filters={defaultFilters()}
        total={10}
        onFiltersChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Firing' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resolved' })).toBeInTheDocument();
  });

  it('Firing is selected by default', () => {
    render(
      <IncidentsToolbar
        filters={defaultFilters()}
        total={10}
        onFiltersChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Firing' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('calls onFiltersChange when switching to Resolved', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <IncidentsToolbar filters={defaultFilters()} total={10} onFiltersChange={onChange} />,
    );
    await user.click(screen.getByRole('button', { name: 'Resolved' }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ mode: 'resolved' }));
  });

  it('hides time range when mode is firing', () => {
    render(
      <IncidentsToolbar
        filters={defaultFilters({ mode: 'firing' })}
        total={10}
        onFiltersChange={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText('Time range filter')).not.toBeInTheDocument();
  });

  it('shows time range when mode is resolved', () => {
    render(
      <IncidentsToolbar
        filters={defaultFilters({ mode: 'resolved' })}
        total={10}
        onFiltersChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Time range')).toBeInTheDocument();
  });

  it('renders pagination with correct item count', () => {
    const { container } = render(
      <IncidentsToolbar
        filters={defaultFilters({ page: 1, pageSize: 50 })}
        total={120}
        onFiltersChange={vi.fn()}
      />,
    );
    const paginationDiv = container.querySelector('.pf-v6-c-pagination');
    expect(paginationDiv).not.toBeNull();
    expect(paginationDiv!.textContent).toContain('120');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <IncidentsToolbar
        filters={defaultFilters()}
        total={10}
        onFiltersChange={vi.fn()}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
