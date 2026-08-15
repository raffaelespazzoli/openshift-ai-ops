import { renderHook } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { KeyboardShortcutsContext, type KeyboardShortcutsContextValue } from '@providers/keyboard-shortcuts-context';
import { useKeyboardShortcuts } from './use-keyboard-shortcuts';

function createWrapper(contextValue: KeyboardShortcutsContextValue) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(KeyboardShortcutsContext, { value: contextValue, children });
  };
}

function fireKey(key: string, target?: HTMLElement) {
  const el = target ?? document.body;
  el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
}

describe('useKeyboardShortcuts', () => {
  const defaultContext: KeyboardShortcutsContextValue = {
    shortcutsEnabled: true,
    toggleShortcuts: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls the action for a matching key', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper(defaultContext),
    });

    fireKey('j');
    expect(action).toHaveBeenCalledOnce();
  });

  it('does not call action for non-matching keys', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper(defaultContext),
    });

    fireKey('k');
    expect(action).not.toHaveBeenCalled();
  });

  it('does not fire when shortcuts are disabled via context', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper({ shortcutsEnabled: false, toggleShortcuts: vi.fn() }),
    });

    fireKey('j');
    expect(action).not.toHaveBeenCalled();
  });

  it('does not fire when disabled via options', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }, { enabled: false }), {
      wrapper: createWrapper(defaultContext),
    });

    fireKey('j');
    expect(action).not.toHaveBeenCalled();
  });

  it('ignores keydown when target is an input element', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper(defaultContext),
    });

    const input = document.createElement('input');
    document.body.appendChild(input);
    fireKey('j', input);
    document.body.removeChild(input);
    expect(action).not.toHaveBeenCalled();
  });

  it('ignores keydown when target is a textarea', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper(defaultContext),
    });

    const textarea = document.createElement('textarea');
    document.body.appendChild(textarea);
    fireKey('j', textarea);
    document.body.removeChild(textarea);
    expect(action).not.toHaveBeenCalled();
  });

  it('ignores keydown when target is a select element', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper(defaultContext),
    });

    const select = document.createElement('select');
    document.body.appendChild(select);
    fireKey('j', select);
    document.body.removeChild(select);
    expect(action).not.toHaveBeenCalled();
  });

  it('ignores keydown when target is contenteditable', () => {
    const action = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper(defaultContext),
    });

    const div = document.createElement('div');
    div.setAttribute('contenteditable', 'true');
    document.body.appendChild(div);
    fireKey('j', div);
    document.body.removeChild(div);
    expect(action).not.toHaveBeenCalled();
  });

  it('unregisters handler on unmount', () => {
    const action = vi.fn();
    const { unmount } = renderHook(() => useKeyboardShortcuts({ j: action }), {
      wrapper: createWrapper(defaultContext),
    });

    unmount();
    fireKey('j');
    expect(action).not.toHaveBeenCalled();
  });
});
