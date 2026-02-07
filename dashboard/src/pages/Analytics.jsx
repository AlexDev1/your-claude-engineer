import React, { useState } from 'react'
import { RefreshCw, Download, Calendar, FileText, FileJson } from 'lucide-react'
import VelocityChart from '../components/VelocityChart'
import EfficiencyMetrics from '../components/EfficiencyMetrics'
import BottleneckPanel from '../components/BottleneckPanel'
import PriorityChart from '../components/PriorityChart'
import ActivityHeatmap from '../components/ActivityHeatmap'
import StateTimeChart from '../components/StateTimeChart'
import ContextBudget from '../components/ContextBudget'
import { useAnalytics, useExport } from '../hooks/useAnalytics'

function Analytics() {
  const [days, setDays] = useState(14)
  const [team, setTeam] = useState('ENG')
  const { data, loading, error, refetch } = useAnalytics(days, team)
  const { exportData, exporting } = useExport()

  const periodOptions = [
    { value: 7, label: '7 days' },
    { value: 14, label: '14 days' },
    { value: 30, label: '30 days' },
    { value: 90, label: '90 days' },
  ]

  return (
    <div className="space-y-6">
      {/* Header with Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2
            className="text-2xl font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            Performance Analytics
          </h2>
          <p
            className="mt-1"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Agent KPIs and productivity metrics
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {/* Period Selector */}
          <div
            className="flex items-center space-x-2 rounded-lg p-1"
            style={{ backgroundColor: 'var(--color-cardBg)' }}
          >
            <Calendar
              className="w-4 h-4 ml-2"
              style={{ color: 'var(--color-textMuted)' }}
            />
            {periodOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => setDays(option.value)}
                className="px-3 py-1.5 text-sm rounded-md transition-colors"
                style={{
                  backgroundColor: days === option.value ? 'var(--color-accent)' : 'transparent',
                  color: days === option.value ? 'white' : 'var(--color-textSecondary)'
                }}
              >
                {option.label}
              </button>
            ))}
          </div>

          {/* Refresh Button */}
          <button
            onClick={refetch}
            disabled={loading}
            className="p-2 rounded-lg transition-colors disabled:opacity-50"
            style={{ backgroundColor: 'var(--color-cardBg)', color: 'var(--color-textSecondary)' }}
            title="Refresh data"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {/* Export Dropdown */}
          <div className="relative group">
            <button
              disabled={exporting}
              className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
              style={{ backgroundColor: 'var(--color-cardBg)', color: 'var(--color-textSecondary)' }}
            >
              <Download className="w-4 h-4" />
              <span className="text-sm">Export</span>
            </button>
            <div
              className="absolute right-0 mt-2 w-48 border rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10"
              style={{
                backgroundColor: 'var(--color-cardBg)',
                borderColor: 'var(--color-border)'
              }}
            >
              <button
                onClick={() => exportData('csv', 'week', team)}
                className="flex items-center space-x-2 w-full px-4 py-2 text-sm rounded-t-lg transition-colors"
                style={{ color: 'var(--color-textSecondary)' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <FileText className="w-4 h-4" />
                <span>Export CSV (week)</span>
              </button>
              <button
                onClick={() => exportData('csv', 'month', team)}
                className="flex items-center space-x-2 w-full px-4 py-2 text-sm transition-colors"
                style={{ color: 'var(--color-textSecondary)' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <FileText className="w-4 h-4" />
                <span>Export CSV (month)</span>
              </button>
              <button
                onClick={() => exportData('json', 'week', team)}
                className="flex items-center space-x-2 w-full px-4 py-2 text-sm rounded-b-lg transition-colors"
                style={{ color: 'var(--color-textSecondary)' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <FileJson className="w-4 h-4" />
                <span>Export JSON (week)</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div
          className="rounded-lg p-4 border"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171'
          }}
        >
          <p className="font-medium">Error loading analytics</p>
          <p className="text-sm mt-1">{error}</p>
          <p className="text-sm mt-2" style={{ color: 'var(--color-textSecondary)' }}>
            Showing demo data instead.
          </p>
        </div>
      )}

      {/* Loading State */}
      {loading && !data && (
        <div className="flex items-center justify-center h-64">
          <div className="flex items-center space-x-3" style={{ color: 'var(--color-textSecondary)' }}>
            <RefreshCw className="w-6 h-6 animate-spin" />
            <span>Loading analytics...</span>
          </div>
        </div>
      )}

      {/* Main Dashboard Grid */}
      {data && (
        <>
          {/* Top Row - Velocity and Efficiency */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <VelocityChart data={data.velocity} />
            <EfficiencyMetrics data={data.efficiency} />
          </div>

          {/* Second Row - Priority and State Time */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <PriorityChart data={data.priority_distribution} />
            <StateTimeChart data={data.bottlenecks?.time_distribution} />
          </div>

          {/* Third Row - Activity Heatmap */}
          <ActivityHeatmap data={data.activity_heatmap} />

          {/* Bottom Row - Bottleneck Detection and Context Budget */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <BottleneckPanel data={data.bottlenecks} />
            </div>
            <ContextBudget refreshInterval={10000} />
          </div>

          {/* Summary Stats Footer */}
          <div
            className="rounded-xl p-4 border"
            style={{
              backgroundColor: 'var(--color-cardBg)',
              borderColor: 'var(--color-cardBorder)'
            }}
          >
            <div
              className="flex items-center justify-between text-sm"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              <span>
                Data period: Last {days} days | Team: {team}
              </span>
              <span>
                Last updated: {new Date().toLocaleTimeString()}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default Analytics
