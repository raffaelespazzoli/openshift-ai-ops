import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect } from 'vitest';
import type { IncidentListItem } from '@models/incident';
import { IncidentsList } from './incidents-list';

expect.extend(toHaveNoViolations);

const ITEMS: IncidentListItem[] = [
  {
    id: '11111111-1111-1111-1111-111111111111',
    state: 'diagnosing',
    severity: 'critical',
    created_at: new Date(Date.now() - 600_000).toISOString(),
    updated_at: new Date(Date.now() - 300_000).toISOString(),
    fast_path: false,
  },
  {
    id: '22222222-2222-2222-2222-222222222222',
    state: 'executing',
    severity: 'warning',
    created_at: new Date(Date.now() - 3_600_000).toISOString(),
    updated_at: new Date(Date.now() - 1_800_000).toISOString(),
    fast_path: true,
  },
];

function renderWithRouter(items: IncidentListItem[]) {
  return render(
    <MemoryRouter>
      <IncidentsList items={items} />
    </MemoryRouter>,
  );
}

describe('IncidentsList', () => {
  it('renders all incident rows', () => {
    renderWithRouter(ITEMS);
    expect(screen.getByText('critical')).toBeInTheDocument();
    expect(screen.getByText('warning')).toBeInTheDocument();
  });

  it('displays state labels with proper formatting', () => {
    renderWithRouter(ITEMS);
    expect(screen.getByText('Diagnosing')).toBeInTheDocument();
    expect(screen.getByText('Executing')).toBeInTheDocument();
  });

  it('shows fast-path label when applicable', () => {
    renderWithRouter(ITEMS);
    expect(screen.getByText('Fast-Path')).toBeInTheDocument();
  });

  it('expands details on toggle click', async () => {
    const user = userEvent.setup();
    renderWithRouter(ITEMS);
    const toggles = screen.getAllByRole('button', { name: /expand/i });
    await user.click(toggles[0]!);
    const expandedSection = screen.getByLabelText(
      `Details for incident ${ITEMS[0]!.id}`,
    );
    expect(expandedSection).not.toHaveAttribute('hidden');
    expect(expandedSection).toHaveTextContent(ITEMS[0]!.id);
  });

  it('renders aria-label on DataListItems with state info', () => {
    renderWithRouter(ITEMS);
    expect(
      screen.getByLabelText(/Root-Cause Event: Diagnosing, severity critical, collapsed/),
    ).toBeInTheDocument();
  });

  it('renders aria-controls on toggle buttons linking to content', () => {
    renderWithRouter(ITEMS);
    const toggles = screen.getAllByRole('button', { name: /expand/i });
    expect(toggles[0]).toHaveAttribute(
      'aria-controls',
      `content-${ITEMS[0]!.id}`,
    );
  });

  it('applies focused row styling when focusedIndex is set', () => {
    render(
      <MemoryRouter>
        <IncidentsList items={ITEMS} focusedIndex={0} />
      </MemoryRouter>,
    );
    const focusedItem = screen.getByLabelText(/Root-Cause Event: Diagnosing/);
    expect(focusedItem).toHaveStyle({
      outline: '2px solid var(--pf-t--global--border--color--hover)',
    });
  });

  it('sets aria-activedescendant when item is focused', () => {
    render(
      <MemoryRouter>
        <IncidentsList items={ITEMS} focusedIndex={1} />
      </MemoryRouter>,
    );
    const list = screen.getByRole('list', { name: 'Incidents list' });
    expect(list).toHaveAttribute('aria-activedescendant', ITEMS[1]!.id);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderWithRouter(ITEMS);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
