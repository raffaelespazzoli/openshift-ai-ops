import { renderHook } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { KeyboardShortcutsContext, type KeyboardShortcutsContextValue } from '@providers/keyboard-shortcuts-context';
import { useDetailKeyboardNav } from './use-detail-keyboard-nav';

const contextValue: KeyboardShortcutsContextValue = {
  shortcutsEnabled: true,
  toggleShortcuts: vi.fn(),
};

function createWrapper() {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      MemoryRouter,
      { initialEntries: [{ pathname: '/incidents/inc-1', state: { returnSearch: '?mode=firing' } }] },
      createElement(KeyboardShortcutsContext, { value: contextValue, children }),
    );
  };
}

function fireKey(key: string) {
  document.body.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
}

describe('useDetailKeyboardNav', () => {
  const defaultOpts = {
    incidentState: 'awaiting_approval',
    expandedStage: 3 as number | null,
    stageCount: 6,
    onStageSelect: vi.fn(),
    onApprove: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls onStageSelect when pressing 1-6', () => {
    renderHook(() => useDetailKeyboardNav(defaultOpts), { wrapper: createWrapper() });
    fireKey('1');
    expect(defaultOpts.onStageSelect).toHaveBeenCalledWith(0);
    fireKey('4');
    expect(defaultOpts.onStageSelect).toHaveBeenCalledWith(3);
  });

  it('calls onApprove on "a" when state is awaiting_approval and remediation expanded', () => {
    renderHook(() => useDetailKeyboardNav(defaultOpts), { wrapper: createWrapper() });
    fireKey('a');
    expect(defaultOpts.onApprove).toHaveBeenCalledOnce();
  });

  it('does NOT call onApprove when state is not awaiting_approval', () => {
    const opts = { ...defaultOpts, incidentState: 'diagnosing', onApprove: vi.fn() };
    renderHook(() => useDetailKeyboardNav(opts), { wrapper: createWrapper() });
    fireKey('a');
    expect(opts.onApprove).not.toHaveBeenCalled();
  });

  it('does NOT call onApprove when remediation panel is not expanded', () => {
    const opts = { ...defaultOpts, expandedStage: 1, onApprove: vi.fn() };
    renderHook(() => useDetailKeyboardNav(opts), { wrapper: createWrapper() });
    fireKey('a');
    expect(opts.onApprove).not.toHaveBeenCalled();
  });
});
