import { useTheme } from '@/context/ThemeContext';
import { Moon, Sun } from 'lucide-react';

export const ThemeToggle = ({ className = '' }) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className={`flex items-center gap-2 transition-colors ${className}`}
      data-testid="theme-toggle"
      aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
    >
      {theme === 'light' ? (
        <>
          <Moon className="w-4 h-4" />
          <span className="font-mono text-xs uppercase tracking-widest">Dark Mode</span>
        </>
      ) : (
        <>
          <Sun className="w-4 h-4" />
          <span className="font-mono text-xs uppercase tracking-widest">Light Mode</span>
        </>
      )}
    </button>
  );
};

export default ThemeToggle;
