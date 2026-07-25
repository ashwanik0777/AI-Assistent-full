'use client';

import { Sun, Moon } from 'lucide-react';
import { useTheme } from './theme-provider';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      id="theme-toggle"
      onClick={toggleTheme}
      className="focus-ring transition-base relative flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface-secondary hover:bg-surface-tertiary"
      aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
    >
      <Sun
        className={`h-[18px] w-[18px] text-warning transition-all duration-300 ${
          theme === 'light'
            ? 'rotate-0 scale-100 opacity-100'
            : 'rotate-90 scale-0 opacity-0'
        }`}
        style={{ position: theme === 'light' ? 'relative' : 'absolute' }}
      />
      <Moon
        className={`h-[18px] w-[18px] text-primary-light transition-all duration-300 ${
          theme === 'dark'
            ? 'rotate-0 scale-100 opacity-100'
            : '-rotate-90 scale-0 opacity-0'
        }`}
        style={{ position: theme === 'dark' ? 'relative' : 'absolute' }}
      />
    </button>
  );
}
