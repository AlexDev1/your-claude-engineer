import React, { useState, useEffect } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { BarChart3, Activity, ClipboardList, Settings as SettingsIcon, Upload, Download } from 'lucide-react'
import ThemeToggle from './components/ThemeToggle'
import MobileNav from './components/MobileNav'
import { useTheme } from './context/ThemeContext'
import { usePWA } from './hooks/usePWA'

function App() {
  const location = useLocation()
  const { resolvedTheme } = useTheme()
  const { isOnline, canInstall, install } = usePWA()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [showInstallBanner, setShowInstallBanner] = useState(false)

  const navItems = [
    { path: '/tasks', label: 'Tasks', icon: ClipboardList },
    { path: '/analytics', label: 'Analytics', icon: BarChart3 },
    { path: '/import', label: 'Import', icon: Upload },
    { path: '/export', label: 'Export', icon: Download },
    { path: '/settings', label: 'Settings', icon: SettingsIcon },
  ]

  // Show install banner after a delay on mobile
  useEffect(() => {
    if (canInstall) {
      const timer = setTimeout(() => {
        setShowInstallBanner(true)
      }, 5000)
      return () => clearTimeout(timer)
    }
  }, [canInstall])

  // Close mobile menu on route change
  useEffect(() => {
    setIsMobileMenuOpen(false)
  }, [location.pathname])

  const handleInstall = async () => {
    const installed = await install()
    if (installed) {
      setShowInstallBanner(false)
    }
  }

  return (
    <div
      className="min-h-screen transition-colors duration-300"
      style={{ backgroundColor: 'var(--color-bg)' }}
    >
      {/* Offline Indicator */}
      <div
        className={`offline-indicator ${!isOnline ? 'visible offline' : ''}`}
      >
        You are offline. Changes will sync when back online.
      </div>

      {/* Header */}
      <header
        className="border-b px-4 md:px-6 py-3 md:py-4 transition-colors duration-300"
        style={{
          backgroundColor: 'var(--color-headerBg)',
          borderColor: 'var(--color-border)'
        }}
      >
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center space-x-2 md:space-x-3">
            <Activity
              className="w-6 h-6 md:w-8 md:h-8"
              style={{ color: 'var(--color-accent)' }}
            />
            <h1
              className="text-lg md:text-xl font-bold"
              style={{ color: 'var(--color-text)' }}
            >
              <span className="hidden sm:inline">Agent Analytics</span>
              <span className="sm:hidden">Dashboard</span>
            </h1>
          </div>

          <div className="flex items-center space-x-2">
            {/* Desktop Navigation */}
            <nav className="hidden md:flex space-x-2 mr-4">
              {navItems.map(({ path, label, icon: Icon }) => {
                const isActive = location.pathname === path || (location.pathname === '/' && path === '/tasks')
                return (
                  <Link
                    key={path}
                    to={path}
                    className="flex items-center space-x-2 px-3 lg:px-4 py-2 rounded-lg transition-all duration-200 min-h-touch"
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
                    <span className="hidden lg:inline">{label}</span>
                  </Link>
                )
              })}
            </nav>

            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 md:px-6 py-4 md:py-8 pb-24 md:pb-8">
        <Outlet />
      </main>

      {/* Mobile Navigation */}
      <MobileNav
        isMenuOpen={isMobileMenuOpen}
        onMenuToggle={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
      />

      {/* PWA Install Banner (Mobile Only) */}
      {showInstallBanner && canInstall && (
        <div className="pwa-install-banner md:hidden">
          <button
            onClick={() => setShowInstallBanner(false)}
            className="close-btn"
            aria-label="Close"
          >
            <span className="text-lg">x</span>
          </button>
          <div className="flex items-center gap-4">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ backgroundColor: 'var(--color-accent)' }}
            >
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <h3
                className="font-semibold text-sm"
                style={{ color: 'var(--color-text)' }}
              >
                Install Agent Dashboard
              </h3>
              <p
                className="text-xs"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                Get quick access from your home screen
              </p>
            </div>
            <button
              onClick={handleInstall}
              className="px-4 py-2 rounded-lg text-sm font-medium"
              style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
            >
              Install
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
