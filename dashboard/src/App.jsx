import React from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { BarChart3, Activity, ClipboardList, Settings as SettingsIcon } from 'lucide-react'
import ThemeToggle from './components/ThemeToggle'
import { useTheme } from './context/ThemeContext'

function App() {
  const location = useLocation()
  const { resolvedTheme } = useTheme()

  const navItems = [
    { path: '/tasks', label: 'Tasks', icon: ClipboardList },
    { path: '/analytics', label: 'Analytics', icon: BarChart3 },
    { path: '/settings', label: 'Settings', icon: SettingsIcon },
  ]

  return (
    <div
      className="min-h-screen transition-colors duration-300"
      style={{ backgroundColor: 'var(--color-bg)' }}
    >
      {/* Header */}
      <header
        className="border-b px-6 py-4 transition-colors duration-300"
        style={{
          backgroundColor: 'var(--color-headerBg)',
          borderColor: 'var(--color-border)'
        }}
      >
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center space-x-3">
            <Activity
              className="w-8 h-8"
              style={{ color: 'var(--color-accent)' }}
            />
            <h1
              className="text-xl font-bold"
              style={{ color: 'var(--color-text)' }}
            >
              Agent Analytics
            </h1>
          </div>
          <div className="flex items-center space-x-2">
            <nav className="flex space-x-2 mr-4">
              {navItems.map(({ path, label, icon: Icon }) => {
                const isActive = location.pathname === path || (location.pathname === '/' && path === '/tasks')
                return (
                  <Link
                    key={path}
                    to={path}
                    className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-all duration-200"
                    style={{
                      backgroundColor: isActive ? 'var(--color-accent)' : 'transparent',
                      color: isActive ? 'white' : 'var(--color-textSecondary)'
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'
                        e.currentTarget.style.color = 'var(--color-text)'
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.backgroundColor = 'transparent'
                        e.currentTarget.style.color = 'var(--color-textSecondary)'
                      }
                    }}
                  >
                    <Icon className="w-5 h-5" />
                    <span>{label}</span>
                  </Link>
                )
              })}
            </nav>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}

export default App
