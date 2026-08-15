import { createContext, useCallback, useState, type ReactNode } from 'react';

const STORAGE_KEY = 'keyboard-shortcuts-enabled';

function readPersistedValue(): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored !== 'false';
  } catch {
    return true;
  }
}

export interface KeyboardShortcutsContextValue {
  shortcutsEnabled: boolean;
  toggleShortcuts: () => void;
}

export const KeyboardShortcutsContext = createContext<KeyboardShortcutsContextValue>({
  shortcutsEnabled: true,
  toggleShortcuts: () => {},
});

export function KeyboardShortcutsProvider({ children }: { children: ReactNode }) {
  const [shortcutsEnabled, setShortcutsEnabled] = useState(readPersistedValue);

  const toggleShortcuts = useCallback(() => {
    setShortcutsEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // localStorage unavailable
      }
      return next;
    });
  }, []);

  return (
    <KeyboardShortcutsContext value={{ shortcutsEnabled, toggleShortcuts }}>
      {children}
    </KeyboardShortcutsContext>
  );
}
