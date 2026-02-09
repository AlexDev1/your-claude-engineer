import React, { useState } from 'react'
import { Sun, Moon, Monitor, Palette, Check, RotateCcw } from 'lucide-react'
import { useTheme, THEMES, ACCENT_PRESETS } from '../context/ThemeContext'

function Settings() {
  const { themeMode, resolvedTheme, accentColor, setTheme, setAccent } = useTheme()
  const [customHex, setCustomHex] = useState(accentColor?.value || '')
  const [hexError, setHexError] = useState('')

  const themeOptions = [
    { id: 'light', label: 'Светлая', icon: Sun, description: 'Чистая и яркая' },
    { id: 'dark', label: 'Тёмная', icon: Moon, description: 'Комфортная для глаз' },
    { id: 'midnight', label: 'Полночь', icon: Palette, description: 'Глубокий индиго' },
    { id: 'system', label: 'Системная', icon: Monitor, description: 'Как в ОС' },
  ]

  const validateHex = (hex) => {
    const cleanHex = hex.startsWith('#') ? hex : `#${hex}`
    const isValid = /^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/.test(cleanHex)
    return isValid ? cleanHex : null
  }

  const handleCustomHexChange = (e) => {
    const value = e.target.value
    setCustomHex(value)
    setHexError('')
  }

  const applyCustomHex = () => {
    const validHex = validateHex(customHex)
    if (validHex) {
      // Generate a hover color (slightly darker)
      const hoverHex = adjustBrightness(validHex, -20)
      setAccent({ name: 'Custom', value: validHex, hover: hoverHex })
      setHexError('')
    } else {
      setHexError('Неверный HEX-цвет')
    }
  }

  const adjustBrightness = (hex, amount) => {
    const num = parseInt(hex.slice(1), 16)
    const r = Math.max(0, Math.min(255, (num >> 16) + amount))
    const g = Math.max(0, Math.min(255, ((num >> 8) & 0x00FF) + amount))
    const b = Math.max(0, Math.min(255, (num & 0x0000FF) + amount))
    return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`
  }

  const resetAccent = () => {
    setAccent(null)
    setCustomHex('')
    setHexError('')
  }

  const currentTheme = THEMES[resolvedTheme]

  return (
    <div className="space-y-8 max-w-3xl">
      {/* Page Header */}
      <div>
        <h2
          className="text-2xl font-bold"
          style={{ color: 'var(--color-text)' }}
        >
          Настройки
        </h2>
        <p style={{ color: 'var(--color-textSecondary)' }} className="mt-1">
          Настройка внешнего вида дашборда
        </p>
      </div>

      {/* Theme Selection */}
      <div
        className="rounded-xl p-6 border"
        style={{
          backgroundColor: 'var(--color-cardBg)',
          borderColor: 'var(--color-cardBorder)'
        }}
      >
        <h3
          className="text-lg font-semibold mb-4"
          style={{ color: 'var(--color-text)' }}
        >
          Тема
        </h3>
        <p
          className="text-sm mb-4"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          Выберите предпочитаемую цветовую схему
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {themeOptions.map((option) => {
            const Icon = option.icon
            const isActive = themeMode === option.id
            return (
              <button
                key={option.id}
                onClick={() => setTheme(option.id)}
                className="relative flex flex-col items-center p-4 rounded-lg border-2 transition-all duration-200"
                style={{
                  backgroundColor: isActive ? 'var(--color-accent)' : 'var(--color-bgSecondary)',
                  borderColor: isActive ? 'var(--color-accent)' : 'var(--color-border)',
                  color: isActive ? 'white' : 'var(--color-text)'
                }}
              >
                {isActive && (
                  <div className="absolute top-2 right-2">
                    <Check className="w-4 h-4" />
                  </div>
                )}
                <Icon className="w-6 h-6 mb-2" />
                <span className="font-medium text-sm">{option.label}</span>
                <span
                  className="text-xs mt-1"
                  style={{ color: isActive ? 'rgba(255,255,255,0.8)' : 'var(--color-textMuted)' }}
                >
                  {option.description}
                </span>
              </button>
            )
          })}
        </div>

        {/* Current Theme Preview */}
        <div
          className="mt-6 p-4 rounded-lg border"
          style={{
            backgroundColor: 'var(--color-bgSecondary)',
            borderColor: 'var(--color-border)'
          }}
        >
          <div className="flex items-center justify-between">
            <div>
              <p
                className="text-sm font-medium"
                style={{ color: 'var(--color-text)' }}
              >
                Текущая: {currentTheme?.name || resolvedTheme}
              </p>
              <p
                className="text-xs"
                style={{ color: 'var(--color-textMuted)' }}
              >
                {themeMode === 'system' ? `Системная (${resolvedTheme})` : 'Ручной выбор'}
              </p>
            </div>
            <div className="flex items-center space-x-2">
              <div
                className="w-4 h-4 rounded-full border"
                style={{ backgroundColor: currentTheme?.colors.bg, borderColor: 'var(--color-border)' }}
                title="Фон"
              />
              <div
                className="w-4 h-4 rounded-full border"
                style={{ backgroundColor: currentTheme?.colors.cardBg, borderColor: 'var(--color-border)' }}
                title="Карточка"
              />
              <div
                className="w-4 h-4 rounded-full"
                style={{ backgroundColor: 'var(--color-accent)' }}
                title="Акцент"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Accent Color Selection */}
      <div
        className="rounded-xl p-6 border"
        style={{
          backgroundColor: 'var(--color-cardBg)',
          borderColor: 'var(--color-cardBorder)'
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3
              className="text-lg font-semibold"
              style={{ color: 'var(--color-text)' }}
            >
              Цвет акцента
            </h3>
            <p
              className="text-sm"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              Настройте основной цвет акцента
            </p>
          </div>
          {accentColor && (
            <button
              onClick={resetAccent}
              className="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-colors"
              style={{
                backgroundColor: 'var(--color-bgSecondary)',
                color: 'var(--color-textSecondary)'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--color-bgSecondary)'}
            >
              <RotateCcw className="w-4 h-4" />
              <span>Сброс</span>
            </button>
          )}
        </div>

        {/* Preset Colors */}
        <div className="mb-6">
          <p
            className="text-xs font-medium uppercase tracking-wider mb-3"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Пресеты
          </p>
          <div className="flex flex-wrap gap-3">
            {ACCENT_PRESETS.map((preset) => {
              const isActive = accentColor?.value === preset.value
              return (
                <button
                  key={preset.name}
                  onClick={() => setAccent(preset)}
                  className="relative flex items-center space-x-2 px-4 py-2 rounded-lg border-2 transition-all duration-200"
                  style={{
                    borderColor: isActive ? preset.value : 'var(--color-border)',
                    backgroundColor: isActive ? `${preset.value}20` : 'var(--color-bgSecondary)'
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.borderColor = preset.value
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.borderColor = 'var(--color-border)'
                    }
                  }}
                >
                  <div
                    className="w-5 h-5 rounded-full"
                    style={{ backgroundColor: preset.value }}
                  />
                  <span
                    className="text-sm font-medium"
                    style={{ color: 'var(--color-text)' }}
                  >
                    {preset.name}
                  </span>
                  {isActive && (
                    <Check className="w-4 h-4" style={{ color: preset.value }} />
                  )}
                </button>
              )
            })}
          </div>
        </div>

        {/* Custom Color Input */}
        <div>
          <p
            className="text-xs font-medium uppercase tracking-wider mb-3"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Свой цвет
          </p>
          <div className="flex items-center space-x-3">
            <div className="relative flex-1">
              <span
                className="absolute left-3 top-1/2 -translate-y-1/2 text-sm"
                style={{ color: 'var(--color-textMuted)' }}
              >
                #
              </span>
              <input
                type="text"
                value={customHex.replace('#', '')}
                onChange={handleCustomHexChange}
                placeholder="3b82f6"
                maxLength={7}
                className="w-full pl-7 pr-3 py-2 rounded-lg border text-sm transition-colors"
                style={{
                  backgroundColor: 'var(--color-inputBg)',
                  borderColor: hexError ? '#ef4444' : 'var(--color-inputBorder)',
                  color: 'var(--color-text)'
                }}
                onKeyDown={(e) => e.key === 'Enter' && applyCustomHex()}
              />
            </div>
            <div
              className="w-10 h-10 rounded-lg border"
              style={{
                backgroundColor: validateHex(customHex) || 'var(--color-bgSecondary)',
                borderColor: 'var(--color-border)'
              }}
            />
            <button
              onClick={applyCustomHex}
              disabled={!customHex}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              style={{
                backgroundColor: 'var(--color-accent)',
                color: 'white'
              }}
            >
              Применить
            </button>
          </div>
          {hexError && (
            <p className="mt-2 text-sm" style={{ color: '#ef4444' }}>
              {hexError}
            </p>
          )}
        </div>

        {/* Preview Section */}
        <div className="mt-6">
          <p
            className="text-xs font-medium uppercase tracking-wider mb-3"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Предпросмотр
          </p>
          <div
            className="p-4 rounded-lg border"
            style={{
              backgroundColor: 'var(--color-bgSecondary)',
              borderColor: 'var(--color-border)'
            }}
          >
            <div className="flex flex-wrap gap-3">
              <button
                className="px-4 py-2 rounded-lg text-sm font-medium"
                style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
              >
                Основная кнопка
              </button>
              <button
                className="px-4 py-2 rounded-lg text-sm font-medium border"
                style={{
                  borderColor: 'var(--color-accent)',
                  color: 'var(--color-accent)',
                  backgroundColor: 'transparent'
                }}
              >
                Контурная кнопка
              </button>
              <span
                className="px-3 py-1 rounded-full text-xs font-medium"
                style={{
                  backgroundColor: 'var(--color-accentMuted)',
                  color: 'var(--color-accent)'
                }}
              >
                Бейдж
              </span>
              <a
                href="#"
                onClick={(e) => e.preventDefault()}
                className="text-sm underline"
                style={{ color: 'var(--color-accent)' }}
              >
                Ссылка
              </a>
            </div>
            <div className="mt-4 flex items-center space-x-4">
              <div className="flex-1 h-2 rounded-full" style={{ backgroundColor: 'var(--color-bgTertiary)' }}>
                <div
                  className="h-full rounded-full"
                  style={{ backgroundColor: 'var(--color-accent)', width: '65%' }}
                />
              </div>
              <span className="text-sm" style={{ color: 'var(--color-accent)' }}>65%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Info Section */}
      <div
        className="rounded-xl p-4 border"
        style={{
          backgroundColor: 'var(--color-bgSecondary)',
          borderColor: 'var(--color-border)'
        }}
      >
        <p className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
          Ваши настройки сохраняются автоматически и действуют между сессиями.
        </p>
      </div>
    </div>
  )
}

export default Settings
