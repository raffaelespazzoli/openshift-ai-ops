import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect } from 'vitest';
import { ConfidenceBadge } from './confidence-badge';

expect.extend(toHaveNoViolations);

describe('ConfidenceBadge', () => {
  it('renders high confidence (≥0.8) with green label', () => {
    render(<ConfidenceBadge confidence={0.92} />);
    expect(screen.getByText('92%')).toBeInTheDocument();
  });

  it('renders medium confidence (0.5–0.79) with orange label', () => {
    render(<ConfidenceBadge confidence={0.67} />);
    expect(screen.getByText('67%')).toBeInTheDocument();
  });

  it('renders low confidence (<0.5) with red label', () => {
    render(<ConfidenceBadge confidence={0.34} />);
    expect(screen.getByText('34%')).toBeInTheDocument();
  });

  it('rounds correctly', () => {
    render(<ConfidenceBadge confidence={0.999} />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<ConfidenceBadge confidence={0.85} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
