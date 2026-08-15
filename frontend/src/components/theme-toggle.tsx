import { useState, useCallback } from 'react';
import { MoonIcon, SunIcon } from '@patternfly/react-icons';
import { Button } from '@patternfly/react-core';

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(() => {
    return document.documentElement.classList.contains('pf-v6-theme-dark');
  });

  const toggleTheme = useCallback(() => {
    const htmlEl = document.documentElement;
    if (isDark) {
      htmlEl.classList.remove('pf-v6-theme-dark');
    } else {
      htmlEl.classList.add('pf-v6-theme-dark');
    }
    setIsDark(!isDark);
  }, [isDark]);

  return (
    <Button
      variant="plain"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={toggleTheme}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}
