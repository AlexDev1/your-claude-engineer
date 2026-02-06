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
          <h2 className="text-2xl font-bold text-white">Performance Analytics</h2>
          <p className="text-gray-400 mt-1">
            Agent KPIs and productivity metrics
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {/* Period Selector */}
          <div className="flex items-center space-x-2 bg-gray-800 rounded-lg p-1">
            <Calendar className="w-4 h-4 text-gray-400 ml-2" />
            {periodOptions.map((option) => (
              <button
                key={option.value}
                onClick={() => setDays(option.value)}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  days === option.value
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          {/* Refresh Button */}
          <button
            onClick={refetch}
            disabled={loading}
            className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh data"
          >
            <RefreshCw className={`w-5 h-5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {/* Export Dropdown */}
          <div className="relative group">
            <button
              disabled={exporting}
              className="flex items-center space-x-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
            >
              <Download className="w-4 h-4 text-gray-400" />
              <span className="text-sm text-gray-300">Export</span>
            </button>
            <div className="absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
              <button
                onClick={() => exportData('csv', 'week', team)}
                className="flex items-center space-x-2 w-full px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-t-lg"
              >
                <FileText className="w-4 h-4" />
                <span>Export CSV (week)</span>
              </button>
              <button
                onClick={() => exportData('csv', 'month', team)}
                className="flex items-center space-x-2 w-full px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
              >
                <FileText className="w-4 h-4" />
                <span>Export CSV (month)</span>
              </button>
              <button
                onClick={() => exportData('json', 'week', team)}
                className="flex items-center space-x-2 w-full px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-b-lg"
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
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-red-400">
          <p className="font-medium">Error loading analytics</p>
          <p className="text-sm mt-1">{error}</p>
          <p className="text-sm mt-2 text-gray-400">Showing demo data instead.</p>
        </div>
      )}

      {/* Loading State */}
      {loading && !data && (
        <div className="flex items-center justify-center h-64">
          <div className="flex items-center space-x-3 text-gray-400">
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
          <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700/50">
            <div className="flex items-center justify-between text-sm text-gray-400">
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
