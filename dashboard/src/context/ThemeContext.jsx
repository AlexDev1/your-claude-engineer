import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'

// Определения тем
export const THEMES = {
  light: {
    name: 'Light',
    colors: {
      bg: '#ffffff',
      bgSecondary: '#f3f4f6',
      bgTertiary: '#e5e7eb',
      text: '#1a1a1a',
      textSecondary: '#4b5563',
      textMuted: '#6b7280',
      border: '#d1d5db',
      borderSecondary: '#e5e7eb',
      accent: '#3b82f6',
      accentHover: '#2563eb',
      accentMuted: '#93c5fd',
      cardBg: '#ffffff',
      cardBorder: '#e5e7eb',
      headerBg: '#f9fafb',
      inputBg: '#ffffff',
      inputBorder: '#d1d5db',
      shadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
      shadowLg: '0 10px 15px rgba(0, 0, 0, 0.1)',
    }
  },
  dark: {
    name: 'Dark',
    colors: {
      bg: '#0a0a0a',
      bgSecondary: '#1f1f1f',
      bgTertiary: '#2a2a2a',
      text: '#fafafa',
      textSecondary: '#a1a1aa',
      textMuted: '#71717a',
      border: '#3f3f46',
      borderSecondary: '#27272a',
      accent: '#60a5fa',
      accentHover: '#3b82f6',
      accentMuted: '#1e40af',
      cardBg: '#18181b',
      cardBorder: '#27272a',
      headerBg: '#18181b',
      inputBg: '#27272a',
      inputBorder: '#3f3f46',
      shadow: '0 1px 3px rgba(0, 0, 0, 0.4)',
      shadowLg: '0 10px 15px rgba(0, 0, 0, 0.4)',
    }
  },
  midnight: {
    name: 'Midnight',
    colors: {
      bg: '#1e1b4b',
      bgSecondary: '#312e81',
      bgTertiary: '#3730a3',
      text: '#e0e7ff',
      textSecondary: '#a5b4fc',
      textMuted: '#818cf8',
      border: '#4338ca',
      borderSecondary: '#3730a3',
      accent: '#818cf8',
      accentHover: '#a5b4fc',
      accentMuted: '#4f46e5',
      cardBg: '#312e81',
      cardBorder: '#4338ca',
      headerBg: '#1e1b4b',
      inputBg: '#3730a3',
      inputBorder: '#4338ca',
      shadow: '0 1px 3px rgba(0, 0, 0, 0.4)',
      shadowLg: '0 10px 15px rgba(0, 0, 0, 0.4)',
    }
  }
}

// Предустановленные цвета акцента
export const ACCENT_PRESETS = [
  { name: 'Blue', value: '#3b82f6', hover: '#2563eb' },
  { name: 'Purple', value: '#8b5cf6', hover: '#7c3aed' },
  { name: 'Green', value: '#10b981', hover: '#059669' },
  { name: 'Orange', value: '#f97316', hover: '#ea580c' },
  { name: 'Pink', value: '#ec4899', hover: '#db2777' },
]

const ThemeContext = createContext(null)

const THEME_STORAGE_KEY = 'agent-dashboard-theme'
const ACCENT_STORAGE_KEY = 'agent-dashboard-accent'

export function ThemeProvider({ children }) {
  const [themeMode, setThemeMode] = useState('system') // 'light', 'dark', 'midnight', 'system'
  const [resolvedTheme, setResolvedTheme] = useState('dark')
  const [accentColor, setAccentColor] = useState(null) // null означает использовать тему по умолчанию
  const [isLoaded, setIsLoaded] = useState(false)

  // Загрузить сохранённые настройки при монтировании
  useEffect(() => {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY)
    const savedAccent = localStorage.getItem(ACCENT_STORAGE_KEY)

    if (savedTheme) {
      setThemeMode(savedTheme)
    }
    if (savedAccent) {
      try {
        setAccentColor(JSON.parse(savedAccent))
      } catch (e) {
        // Неверный JSON, игнорировать
      }
    }
    setIsLoaded(true)
  }, [])

  // Обработать системные настройки темы
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const updateResolvedTheme = () => {
      if (themeMode === 'system') {
        setResolvedTheme(mediaQuery.matches ? 'dark' : 'light')
      } else {
        setResolvedTheme(themeMode)
      }
    }

    updateResolvedTheme()
    mediaQuery.addEventListener('change', updateResolvedTheme)

    return () => mediaQuery.removeEventListener('change', updateResolvedTheme)
  }, [themeMode])

  // Применить CSS-переменные при смене темы
  useEffect(() => {
    if (!isLoaded) return

    const theme = THEMES[resolvedTheme]
    if (!theme) return

    const root = document.documentElement

    // Применить цвета темы как CSS-переменные
    Object.entries(theme.colors).forEach(([key, value]) => {
      root.style.setProperty(`--color-${key}`, value)
    })

    // Применить пользовательский цвет акцента, если установлен
    if (accentColor) {
      root.style.setProperty('--color-accent', accentColor.value)
      root.style.setProperty('--color-accentHover', accentColor.hover || accentColor.value)
    }

    // Установить data-атрибут для условного CSS
    root.setAttribute('data-theme', resolvedTheme)
  }, [resolvedTheme, accentColor, isLoaded])

  // Сохранить настройки в localStorage
  useEffect(() => {
    if (!isLoaded) return
    localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode, isLoaded])

  useEffect(() => {
    if (!isLoaded) return
    if (accentColor) {
      localStorage.setItem(ACCENT_STORAGE_KEY, JSON.stringify(accentColor))
    } else {
      localStorage.removeItem(ACCENT_STORAGE_KEY)
    }
  }, [accentColor, isLoaded])

  const setTheme = useCallback((mode) => {
    setThemeMode(mode)
  }, [])

  const setAccent = useCallback((color) => {
    setAccentColor(color)
  }, [])

  const cycleTheme = useCallback(() => {
    const modes = ['light', 'dark', 'midnight']
    const currentIndex = modes.indexOf(resolvedTheme)
    const nextIndex = (currentIndex + 1) % modes.length
    setThemeMode(modes[nextIndex])
  }, [resolvedTheme])

  const value = {
    themeMode,
    resolvedTheme,
    theme: THEMES[resolvedTheme],
    accentColor,
    setTheme,
    setAccent,
    cycleTheme,
    isSystemTheme: themeMode === 'system',
  }

  // Предотвратить мигание нестилизованного контента
  if (!isLoaded) {
    return null
  }

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

export default ThemeContext
