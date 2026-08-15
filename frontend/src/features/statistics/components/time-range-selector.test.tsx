import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, vi } from 'vitest';
import { TimeRangeSelector } from './time-range-selector';

expect.extend(toHaveNoViolations);

describe('TimeRangeSelector', () => {
  it('renders day, week, and month options', () => {
    render(<TimeRangeSelector value="week" onChange={vi.fn()} />);
    expect(screen.getByText('Day')).toBeInTheDocument();
    expect(screen.getByText('Week')).toBeInTheDocument();
    expect(screen.getByText('Month')).toBeInTheDocument();
  });

  it('highlights the selected range', () => {
    render(<TimeRangeSelector value="week" onChange={vi.fn()} />);
    const weekButton = screen.getByText('Week').closest('button');
    expect(weekButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('calls onChange when a different range is selected', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TimeRangeSelector value="week" onChange={onChange} />);

    await user.click(screen.getByText('Day'));
    expect(onChange).toHaveBeenCalledWith('day');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TimeRangeSelector value="week" onChange={vi.fn()} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
