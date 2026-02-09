import React, { useState, useEffect } from 'react'
import { Gauge, AlertTriangle, HardDrive, FileText, History, Brain, ClipboardList, RefreshCw } from 'lucide-react'

const API_BASE = '/api'

// Category icons and colors
const CATEGORY_CONFIG = {
  system_prompt: { icon: FileText, color: 'bg-blue-500', label: 'Системный промпт' },
  files: { icon: HardDrive, color: 'bg-green-500', label: 'Файлы' },
  history: { icon: History, color: 'bg-purple-500', label: 'История' },
  memory: { icon: Brain, color: 'bg-yellow-500', label: 'Память' },
  issue: { icon: ClipboardList, color: 'bg-pink-500', label: 'Контекст задачи' },
}

// Format token count
function formatTokens(count) {
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`
  }
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`
  }
  return count.toString()
}

function ContextBudget({ refreshInterval = 5000 }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)

  const fetchData = async () => {
    try {
      const response = await fetch(`${API_BASE}/context/stats`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const result = await response.json()
      setData(result)
      setError(null)
      setLastUpdate(new Date())
    } catch (err) {
      console.error('Context stats fetch error:', err)
      setError(err.message)
      // Use demo data on error
      setData(generateDemoData())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, refreshInterval)
    return () => clearInterval(interval)
  }, [refreshInterval])

  if (loading && !data) {
    return (
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center justify-center h-32">
          <RefreshCw className="w-6 h-6 text-gray-400 animate-spin" />
        </div>
      </div>
    )
  }

  const usagePercent = data?.usage_percent || 0
  const isWarning = data?.is_warning || usagePercent >= 80
  const isCritical = usagePercent >= 95

  // Calculate gauge angles
  const gaugeAngle = (usagePercent / 100) * 180

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <Gauge className="w-5 h-5 text-blue-500" />
          <h3 className="text-lg font-semibold text-white">Бюджет контекста</h3>
        </div>
        <div className="flex items-center space-x-2">
          {isWarning && (
            <div className={`flex items-center space-x-1 px-2 py-1 rounded-full text-xs ${
              isCritical ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'
            }`}>
              <AlertTriangle className="w-3 h-3" />
              <span>{isCritical ? 'Критично' : 'Внимание'}</span>
            </div>
          )}
          <button
            onClick={fetchData}
            className="p-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 transition-colors"
            title="Обновить"
          >
            <RefreshCw className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Gauge Display */}
      <div className="flex justify-center mb-6">
        <div className="relative w-48 h-24 overflow-hidden">
          {/* Background arc */}
          <div className="absolute inset-0">
            <svg viewBox="0 0 100 50" className="w-full h-full">
              <path
                d="M 5 50 A 45 45 0 0 1 95 50"
                fill="none"
                stroke="#374151"
                strokeWidth="8"
                strokeLinecap="round"
              />
              {/* Filled arc */}
              <path
                d="M 5 50 A 45 45 0 0 1 95 50"
                fill="none"
                stroke={isCritical ? '#ef4444' : isWarning ? '#eab308' : '#3b82f6'}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${(gaugeAngle / 180) * 141.37} 141.37`}
              />
            </svg>
          </div>
          {/* Center text */}
          <div className="absolute inset-0 flex items-end justify-center pb-2">
            <div className="text-center">
              <span className={`text-3xl font-bold ${
                isCritical ? 'text-red-400' : isWarning ? 'text-yellow-400' : 'text-white'
              }`}>
                {usagePercent.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Token Counts */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-gray-700/50 rounded-lg p-3 text-center">
          <div className="text-sm text-gray-400">Использовано</div>
          <div className="text-xl font-semibold text-white">
            {formatTokens(data?.total_used || 0)}
          </div>
        </div>
        <div className="bg-gray-700/50 rounded-lg p-3 text-center">
          <div className="text-sm text-gray-400">Осталось</div>
          <div className="text-xl font-semibold text-green-400">
            {formatTokens(data?.remaining || 0)}
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>0</span>
          <span>{formatTokens(data?.max_tokens || 200000)}</span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${
              isCritical ? 'bg-red-500' : isWarning ? 'bg-yellow-500' : 'bg-blue-500'
            }`}
            style={{ width: `${Math.min(usagePercent, 100)}%` }}
          />
        </div>
      </div>

      {/* Breakdown */}
      <div className="space-y-2">
        <div className="text-sm font-medium text-gray-400 mb-2">Разбивка</div>
        {data?.breakdown && Object.entries(data.breakdown).map(([category, tokens]) => {
          if (tokens === 0) return null
          const config = CATEGORY_CONFIG[category] || {
            icon: FileText,
            color: 'bg-gray-500',
            label: category,
          }
          const Icon = config.icon
          const percent = data.total_used > 0 ? (tokens / data.total_used) * 100 : 0

          return (
            <div key={category} className="flex items-center space-x-3">
              <div className={`w-6 h-6 rounded flex items-center justify-center ${config.color}`}>
                <Icon className="w-3.5 h-3.5 text-white" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">{config.label}</span>
                  <span className="text-sm text-gray-400">
                    {formatTokens(tokens)} ({percent.toFixed(1)}%)
                  </span>
                </div>
                <div className="h-1 bg-gray-700 rounded-full mt-1">
                  <div
                    className={`h-full rounded-full ${config.color}`}
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer */}
      {lastUpdate && (
        <div className="mt-4 pt-3 border-t border-gray-700">
          <div className="text-xs text-gray-500 text-center">
            Обновлено: {lastUpdate.toLocaleTimeString()}
          </div>
        </div>
      )}

      {/* Error indicator */}
      {error && (
        <div className="mt-2 text-xs text-center text-yellow-500">
          Используются демо-данные (API недоступен)
        </div>
      )}
    </div>
  )
}

function generateDemoData() {
  const maxTokens = 200000
  const breakdown = {
    system_prompt: 2283,
    files: 35000,
    history: 12000,
    memory: 1500,
    issue: 800,
  }
  const totalUsed = Object.values(breakdown).reduce((a, b) => a + b, 0)

  return {
    max_tokens: maxTokens,
    total_used: totalUsed,
    remaining: maxTokens - totalUsed,
    usage_percent: (totalUsed / maxTokens) * 100,
    is_warning: false,
    breakdown,
    files_loaded: 12,
    history_messages: 8,
  }
}

export default ContextBudget
