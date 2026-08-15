import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { useListKeyboardNav } from './use-list-keyboard-nav';

const ITEMS = [
  { id: 'item-1' },
  { id: 'item-2' },
  { id: 'item-3' },
];

describe('useListKeyboardNav', () => {
  it('starts with focusedIndex at -1', () => {
    const { result } = renderHook(() => useListKeyboardNav(ITEMS));
    expect(result.current.focusedIndex).toBe(-1);
    expect(result.current.focusedId).toBeUndefined();
  });

  it('moveDown increments focusedIndex', () => {
    const { result } = renderHook(() => useListKeyboardNav(ITEMS));
    act(() => result.current.moveDown());
    expect(result.current.focusedIndex).toBe(0);
    expect(result.current.focusedId).toBe('item-1');
  });

  it('moveDown clamps to last item', () => {
    const { result } = renderHook(() => useListKeyboardNav(ITEMS));
    act(() => result.current.moveDown());
    act(() => result.current.moveDown());
    act(() => result.current.moveDown());
    act(() => result.current.moveDown());
    expect(result.current.focusedIndex).toBe(2);
  });

  it('moveUp decrements focusedIndex', () => {
    const { result } = renderHook(() => useListKeyboardNav(ITEMS));
    act(() => result.current.setFocusedIndex(2));
    act(() => result.current.moveUp());
    expect(result.current.focusedIndex).toBe(1);
  });

  it('moveUp clamps to 0', () => {
    const { result } = renderHook(() => useListKeyboardNav(ITEMS));
    act(() => result.current.moveUp());
    expect(result.current.focusedIndex).toBe(0);
  });

  it('setFocusedIndex sets arbitrary index', () => {
    const { result } = renderHook(() => useListKeyboardNav(ITEMS));
    act(() => result.current.setFocusedIndex(1));
    expect(result.current.focusedIndex).toBe(1);
    expect(result.current.focusedId).toBe('item-2');
  });

  it('scrolls focused element into view', () => {
    const mockEl = document.createElement('div');
    mockEl.id = 'item-1';
    mockEl.scrollIntoView = vi.fn();
    document.body.appendChild(mockEl);

    const { result } = renderHook(() => useListKeyboardNav(ITEMS));
    act(() => result.current.moveDown());

    expect(mockEl.scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
    document.body.removeChild(mockEl);
  });
});
