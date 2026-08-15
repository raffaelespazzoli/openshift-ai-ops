import { useState, useCallback, useEffect, useRef } from 'react';

export function useListKeyboardNav(items: { id: string }[]) {
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const listRef = useRef<HTMLElement>(null);

  const focusedId = focusedIndex >= 0 ? items[focusedIndex]?.id : undefined;

  const moveDown = useCallback(() => {
    setFocusedIndex((prev) => Math.min(prev + 1, items.length - 1));
  }, [items.length]);

  const moveUp = useCallback(() => {
    setFocusedIndex((prev) => Math.max(prev - 1, 0));
  }, []);

  useEffect(() => {
    if (focusedId) {
      document.getElementById(focusedId)?.scrollIntoView({ block: 'nearest' });
    }
  }, [focusedId]);

  return { focusedIndex, focusedId, moveDown, moveUp, listRef, setFocusedIndex };
}
