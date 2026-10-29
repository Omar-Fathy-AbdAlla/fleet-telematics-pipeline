import { createContext, useContext, useEffect, useState } from 'react'

const STORAGE_KEY = 'theme'
const ThemeContext = createContext(null)

// Light by default; the user's choice is kept in localStorage. The "dark" class on <html> turns on the dark: classes.
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => (localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'))

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggleTheme = () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}

// { theme: 'light' | 'dark', toggleTheme }. For colors set in JS (charts, 3D map) that can't use dark: classes.
export const useTheme = () => useContext(ThemeContext)
