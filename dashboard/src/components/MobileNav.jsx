import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Radio, ClipboardList, BarChart3, Play, Settings, Menu, X } from 'lucide-react'

const NAV_ITEMS = [
  { path: '/live', label: 'Монитор', icon: Radio, isHome: true },
  { path: '/tasks', label: 'Задачи', icon: ClipboardList },
  { path: '/analytics', label: 'Аналитика', icon: BarChart3 },
  { path: '/settings', label: 'Настройки', icon: Settings },
]

function MobileNav({ isMenuOpen, onMenuToggle }) {
  const location = useLocation()

  const isActive = (path, isHome) => {
    if (isHome) {
      return location.pathname === '/' || location.pathname === '/live'
    }
    return location.pathname === path
  }

  return (
    <>
      {/* Bottom Tab Bar - Only visible on mobile */}
      <nav
        className="fixed bottom-0 left-0 right-0 z-50 md:hidden border-t"
        style={{
          backgroundColor: 'var(--color-headerBg)',
          borderColor: 'var(--color-border)',
          paddingBottom: 'env(safe-area-inset-bottom)'
        }}
      >
        <div className="flex items-center justify-around h-16">
          {NAV_ITEMS.map(({ path, label, icon: Icon, isHome }) => {
            const active = isActive(path, isHome)
            return (
              <Link
                key={path}
                to={isHome ? '/live' : path}
                className="flex flex-col items-center justify-center min-w-touch min-h-touch px-3 py-2 transition-colors"
                style={{
                  color: active ? 'var(--color-accent)' : 'var(--color-textMuted)'
                }}
              >
                <Icon className="w-6 h-6" />
                <span className="text-xs mt-1 font-medium">{label}</span>
                {active && (
                  <div
                    className="absolute bottom-1 w-1 h-1 rounded-full"
                    style={{ backgroundColor: 'var(--color-accent)' }}
                  />
                )}
              </Link>
            )
          })}

          {/* Menu Button */}
          <button
            onClick={onMenuToggle}
            className="flex flex-col items-center justify-center min-w-touch min-h-touch px-3 py-2 transition-colors"
            style={{ color: isMenuOpen ? 'var(--color-accent)' : 'var(--color-textMuted)' }}
          >
            {isMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            <span className="text-xs mt-1 font-medium">Ещё</span>
          </button>
        </div>
      </nav>

      {/* Mobile Slide-up Menu */}
      {isMenuOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          onClick={onMenuToggle}
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 animate-fade-in"
            style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
          />

          {/* Menu Panel */}
          <div
            className="absolute bottom-16 left-0 right-0 rounded-t-2xl animate-slide-up border-t"
            style={{
              backgroundColor: 'var(--color-cardBg)',
              borderColor: 'var(--color-border)',
              marginBottom: 'env(safe-area-inset-bottom)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4">
              {/* Handle bar */}
              <div className="flex justify-center mb-4">
                <div
                  className="w-10 h-1 rounded-full"
                  style={{ backgroundColor: 'var(--color-border)' }}
                />
              </div>

              {/* Additional Menu Items */}
              <div className="space-y-2">
                <Link
                  to="/replay"
                  onClick={onMenuToggle}
                  className="flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors"
                  style={{
                    backgroundColor: location.pathname.startsWith('/replay') ? 'var(--color-bgTertiary)' : 'transparent',
                    color: 'var(--color-text)'
                  }}
                >
                  <Play className="w-5 h-5" />
                  <span className="text-lg">Воспроизведение</span>
                </Link>

                <Link
                  to="/import"
                  onClick={onMenuToggle}
                  className="flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors"
                  style={{
                    backgroundColor: location.pathname === '/import' ? 'var(--color-bgTertiary)' : 'transparent',
                    color: 'var(--color-text)'
                  }}
                >
                  <span className="text-lg">Импорт данных</span>
                </Link>

                <Link
                  to="/export"
                  onClick={onMenuToggle}
                  className="flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors"
                  style={{
                    backgroundColor: location.pathname === '/export' ? 'var(--color-bgTertiary)' : 'transparent',
                    color: 'var(--color-text)'
                  }}
                >
                  <span className="text-lg">Экспорт данных</span>
                </Link>

                <div
                  className="border-t my-3"
                  style={{ borderColor: 'var(--color-border)' }}
                />

                <button
                  onClick={() => {
                    // Request notification permission
                    if ('Notification' in window) {
                      Notification.requestPermission()
                    }
                    onMenuToggle()
                  }}
                  className="flex items-center space-x-3 w-full px-4 py-3 rounded-lg transition-colors text-left"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  <span>Включить уведомления</span>
                </button>

                <button
                  onClick={() => {
                    // Add to home screen prompt (if available)
                    if (window.deferredPrompt) {
                      window.deferredPrompt.prompt()
                    }
                    onMenuToggle()
                  }}
                  className="flex items-center space-x-3 w-full px-4 py-3 rounded-lg transition-colors text-left"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  <span>Добавить на экран</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default MobileNav
