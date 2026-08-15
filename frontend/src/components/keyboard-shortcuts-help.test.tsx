import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, it, expect, vi } from 'vitest';
import { KeyboardShortcutsContext, type KeyboardShortcutsContextValue } from '@providers/keyboard-shortcuts-context';
import { KeyboardShortcutsHelp } from './keyboard-shortcuts-help';

expect.extend(toHaveNoViolations);

function renderHelp(
  isOpen: boolean,
  ctx?: Partial<KeyboardShortcutsContextValue>,
) {
  const onClose = vi.fn();
  const contextValue: KeyboardShortcutsContextValue = {
    shortcutsEnabled: true,
    toggleShortcuts: vi.fn(),
    ...ctx,
  };

  const { container } = render(
    <KeyboardShortcutsContext value={contextValue}>
      <KeyboardShortcutsHelp isOpen={isOpen} onClose={onClose} />
    </KeyboardShortcutsContext>,
  );

  return { container, onClose, contextValue };
}

describe('KeyboardShortcutsHelp', () => {
  it('renders the modal when open', () => {
    renderHelp(true);
    expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument();
  });

  it('does not render content when closed', () => {
    renderHelp(false);
    expect(screen.queryByText('Keyboard Shortcuts')).not.toBeInTheDocument();
  });

  it('shows all shortcut descriptions', () => {
    renderHelp(true);
    expect(screen.getByText('j / k')).toBeInTheDocument();
    expect(screen.getByText('Navigate down / up in incident list')).toBeInTheDocument();
    expect(screen.getByText('Enter')).toBeInTheDocument();
    expect(screen.getByText('Esc / Backspace')).toBeInTheDocument();
    expect(screen.getByText('1 – 6')).toBeInTheDocument();
    expect(screen.getByText('a')).toBeInTheDocument();
    expect(screen.getByText('?')).toBeInTheDocument();
  });

  it('renders the enable/disable toggle', () => {
    renderHelp(true);
    expect(screen.getByText('Enable keyboard shortcuts')).toBeInTheDocument();
  });

  it('calls toggleShortcuts when the switch is toggled', async () => {
    const user = userEvent.setup();
    const toggleShortcuts = vi.fn();
    renderHelp(true, { toggleShortcuts });

    const toggle = screen.getByRole('switch', { name: /enable keyboard shortcuts/i });
    await user.click(toggle);
    expect(toggleShortcuts).toHaveBeenCalledOnce();
  });

  it('shows switch as checked when shortcuts are enabled', () => {
    renderHelp(true, { shortcutsEnabled: true });
    const toggle = screen.getByRole('switch', { name: /enable keyboard shortcuts/i });
    expect(toggle).toBeChecked();
  });

  it('shows switch as unchecked when shortcuts are disabled', () => {
    renderHelp(true, { shortcutsEnabled: false });
    const toggle = screen.getByRole('switch', { name: /enable keyboard shortcuts/i });
    expect(toggle).not.toBeChecked();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderHelp(true);
    expect(await axe(container)).toHaveNoViolations();
  });
});
