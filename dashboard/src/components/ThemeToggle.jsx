import { useTheme } from '../hooks/useTheme'

// Switches between light and dark mode; the label names the mode it switches to.
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-800"
    >
      {theme === 'dark' ? '☀ Light mode' : '☾ Dark mode'}
    </button>
  )
}
