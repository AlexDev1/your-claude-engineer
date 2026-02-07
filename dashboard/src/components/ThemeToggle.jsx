import React, { useState, useRef, useEffect } from 'react'
import { Sun, Moon, Monitor, Palette } from 'lucide-react'
import { useTheme, THEMES } from '../context/ThemeContext'

function ThemeToggle() {
  const { themeMode, resolvedTheme, setTheme } = useTheme()
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const getIcon = () => {
    if (themeMode === 'system') {
      return <Monitor className="w-5 h-5" />
    }
    if (resolvedTheme === 'light') {
      return <Sun className="w-5 h-5" />
    }
    if (resolvedTheme === 'midnight') {
      return <Palette className="w-5 h-5" />
    }
    return <Moon className="w-5 h-5" />
  }

  const themeOptions = [
    { id: 'light', label: 'Light', icon: Sun },
    { id: 'dark', label: 'Dark', icon: Moon },
    { id: 'midnight', label: 'Midnight', icon: Palette },
    { id: 'system', label: 'System', icon: Monitor },
  ]

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="p-2 rounded-lg transition-all duration-200 themed-button-ghost"
        style={{
          backgroundColor: isOpen ? 'var(--color-bgTertiary)' : 'transparent',
          color: 'var(--color-textSecondary)'
        }}
        title="Change theme"
        aria-label="Change theme"
      >
        {getIcon()}
      </button>

      {isOpen && (
        <div
          className="absolute right-0 mt-2 w-44 rounded-lg shadow-lg border z-50 overflow-hidden"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-border)',
            boxShadow: 'var(--color-shadowLg)'
          }}
        >
          <div
            className="px-3 py-2 text-xs font-medium uppercase tracking-wider border-b"
            style={{
              color: 'var(--color-textMuted)',
              borderColor: 'var(--color-borderSecondary)'
            }}
          >
            Theme
          </div>
          {themeOptions.map((option) => {
            const Icon = option.icon
            const isActive = themeMode === option.id
            return (
              <button
                key={option.id}
                onClick={() => {
                  setTheme(option.id)
                  setIsOpen(false)
                }}
                className="flex items-center w-full px-3 py-2 text-sm transition-colors"
                style={{
                  backgroundColor: isActive ? 'var(--color-accent)' : 'transparent',
                  color: isActive ? 'white' : 'var(--color-text)'
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.backgroundColor = 'transparent'
                  }
                }}
              >
                <Icon className="w-4 h-4 mr-2" />
                <span>{option.label}</span>
                {option.id === 'system' && (
                  <span
                    className="ml-auto text-xs"
                    style={{ color: isActive ? 'rgba(255,255,255,0.7)' : 'var(--color-textMuted)' }}
                  >
                    {resolvedTheme === 'dark' ? 'Dark' : 'Light'}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default ThemeToggle
