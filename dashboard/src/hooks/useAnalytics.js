import { useState, useEffect, useCallback } from 'react'

const API_BASE = '/api/analytics'

// Check if we're in demo mode (no backend available)
const DEMO_MODE = true // Set to false when analytics server is running

export function useAnalytics(days = 14, team = 'ENG') {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)

    // In demo mode, use mock data directly
    if (DEMO_MODE) {
      // Simulate network delay
      await new Promise(resolve => setTimeout(resolve, 500))
      setData(generateMockData(days))
      setLoading(false)
      return
    }

    try {
      const response = await fetch(`${API_BASE}/summary?days=${days}&team=${team}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch analytics: ${response.status}`)
      }
      const result = await response.json()
      setData(result)
    } catch (err) {
      console.error('Analytics fetch error:', err)
      setError(err.message)
      // Use mock data on error for development
      setData(generateMockData(days))
    } finally {
      setLoading(false)
    }
  }, [days, team])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { data, loading, error, refetch: fetchData }
}

export function useExport() {
  const [exporting, setExporting] = useState(false)

  const exportData = async (format = 'csv', period = 'week', team = 'ENG') => {
    setExporting(true)
    try {
      const response = await fetch(
        `${API_BASE}/export?format=${format}&period=${period}&team=${team}`
      )

      if (format === 'csv') {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `analytics_${period}_${team}.csv`
        document.body.appendChild(a)
        a.click()
        a.remove()
        window.URL.revokeObjectURL(url)
      } else {
        const data = await response.json()
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `analytics_${period}_${team}.json`
        document.body.appendChild(a)
        a.click()
        a.remove()
        window.URL.revokeObjectURL(url)
      }
    } catch (err) {
      console.error('Export error:', err)
    } finally {
      setExporting(false)
    }
  }

  return { exportData, exporting }
}

function generateMockData(days = 14) {
  const now = new Date()
  const daily = []

  // Generate consistent but varying data based on days parameter
  let totalCompleted = 0
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    // Use a pseudo-random pattern based on day
    const dayOfYear = Math.floor((date - new Date(date.getFullYear(), 0, 0)) / 86400000)
    const count = ((dayOfYear * 7) % 5) + 1
    totalCompleted += count
    daily.push({
      date: date.toISOString().split('T')[0],
      count,
    })
  }

  // Calculate trend
  const recentDays = daily.slice(-7)
  const previousDays = daily.slice(-14, -7)
  const recentSum = recentDays.reduce((sum, d) => sum + d.count, 0)
  const previousSum = previousDays.reduce((sum, d) => sum + d.count, 0)
  const trend = recentSum > previousSum * 1.1 ? 'up' : recentSum < previousSum * 0.9 ? 'down' : 'stable'

  return {
    velocity: {
      daily,
      weekly_avg: Math.round((totalCompleted / days) * 7 * 10) / 10,
      trend,
      total_completed: totalCompleted,
    },
    efficiency: {
      success_rate: 87.5,
      avg_completion_time_hours: 3.2,
      tasks_done: 28,
      tasks_cancelled: 4,
      tasks_in_progress: 3,
      tasks_todo: 8,
    },
    bottlenecks: {
      stuck_tasks: [
        { identifier: 'ENG-15', title: 'Complex refactoring task', hours_stuck: 8.5, priority: 'high' },
        { identifier: 'ENG-22', title: 'Integration tests', hours_stuck: 4.2, priority: 'medium' },
      ],
      avg_retry_rate: 1.8,
      time_distribution: {
        'Todo': 2.1,
        'In Progress': 3.8,
        'Done': 0,
      },
      recommendations: [
        'Task ENG-15 stuck for 8.5h. Prioritize resolution.',
        'Average time in "In Progress" is high. Break down tasks into smaller units.',
      ],
      longest_stuck: { identifier: 'ENG-15', title: 'Complex refactoring task', hours_stuck: 8.5 },
    },
    priority_distribution: {
      urgent: 3,
      high: 12,
      medium: 18,
      low: 10,
    },
    activity_heatmap: generateHeatmapData(),
  }
}

function generateHeatmapData() {
  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
  const data = []

  for (const day of days) {
    for (let hour = 0; hour < 24; hour++) {
      const isWorkHour = hour >= 9 && hour <= 18 && !['Saturday', 'Sunday'].includes(day)
      data.push({
        day,
        hour,
        count: isWorkHour ? Math.floor(Math.random() * 5) : Math.floor(Math.random() * 2),
      })
    }
  }

  return data
}
