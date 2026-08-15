import { useEffect, useCallback, useContext } from 'react';
import { KeyboardShortcutsContext } from '@providers/keyboard-shortcuts-context';

const INTERACTIVE_SELECTOR =
  'input, textarea, select, button, a, [contenteditable], [role="button"], [role="link"], [role="tab"], [role="menuitem"]';

export function useKeyboardShortcuts(
  shortcuts: Record<string, () => void>,
  options?: { enabled?: boolean; containerSelector?: string },
) {
  const { shortcutsEnabled } = useContext(KeyboardShortcutsContext);

  const handler = useCallback(
    (event: KeyboardEvent) => {
      if (!shortcutsEnabled || options?.enabled === false) return;

      const target = event.target as HTMLElement | null;
      if (target) {
        if (target.isContentEditable || target.getAttribute?.('contenteditable') === 'true') return;
        if (target.matches(INTERACTIVE_SELECTOR)) {
          if (event.key === 'Enter' || event.key === ' ') return;
          const tagName = target.tagName?.toLowerCase();
          if (tagName && ['input', 'textarea', 'select'].includes(tagName)) return;
          if (target.matches('button, a, [role="button"], [role="link"], [role="tab"], [role="menuitem"]')) return;
        }
      }

      if (event.key === 'Enter' && options?.containerSelector) {
        const container = document.querySelector(options.containerSelector);
        if (!container?.contains(document.activeElement) && document.activeElement !== container) {
          return;
        }
      }

      const action = shortcuts[event.key];
      if (action) {
        event.preventDefault();
        action();
      }
    },
    [shortcuts, shortcutsEnabled, options?.enabled, options?.containerSelector],
  );

  useEffect(() => {
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [handler]);
}
