import { useEffect, useCallback, useContext } from 'react';
import { KeyboardShortcutsContext } from '@providers/keyboard-shortcuts-context';

export function useKeyboardShortcuts(
  shortcuts: Record<string, () => void>,
  options?: { enabled?: boolean },
) {
  const { shortcutsEnabled } = useContext(KeyboardShortcutsContext);

  const handler = useCallback(
    (event: KeyboardEvent) => {
      if (!shortcutsEnabled || options?.enabled === false) return;

      const target = event.target as HTMLElement | null;
      if (target) {
        const tagName = target.tagName?.toLowerCase();
        if (tagName && ['input', 'textarea', 'select'].includes(tagName)) return;
        if (target.isContentEditable || target.getAttribute?.('contenteditable') === 'true') return;
      }

      const action = shortcuts[event.key];
      if (action) {
        event.preventDefault();
        action();
      }
    },
    [shortcuts, shortcutsEnabled, options?.enabled],
  );

  useEffect(() => {
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [handler]);
}
