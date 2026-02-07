import React, { useState, useMemo } from 'react'
import { Clock, CheckCircle, XCircle, Loader2, Calendar, ChevronLeft, ChevronRight } from 'lucide-react'

/**
 * Session status colors
 */
const STATUS_COLORS = {
  success: '#22c55e',
  failed: '#ef4444',
  in_progress: '#6b7280',
  cancelled: '#f59e0b',
}

/**
 * Session Timeline Graph component
 * Shows horizontal timeline with session blocks for the current day
 *
 * @param {Object} props
 * @param {Array} props.sessions - List of session data
 * @param {Date} props.selectedDate - Currently selected date
 * @param {function} props.onDateChange - Callback when date changes
 */
function SessionTimeline({ sessions = [], selectedDate = new Date(), onDateChange }) {
  const [hoveredSession, setHoveredSession] = useState(null)
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 })

  // Filter sessions for selected date
  const daySessions = useMemo(() => {
    const startOfDay = new Date(selectedDate)
    startOfDay.setHours(0, 0, 0, 0)
    const endOfDay = new Date(selectedDate)
    endOfDay.setHours(23, 59, 59, 999)

    return sessions.filter(session => {
      const sessionStart = new Date(session.startTime)
      return sessionStart >= startOfDay && sessionStart <= endOfDay
    }).sort((a, b) => new Date(a.startTime) - new Date(b.startTime))
  }, [sessions, selectedDate])

  // Calculate timeline hours (0-24)
  const hours = Array.from({ length: 24 }, (_, i) => i)

  // Calculate session position and width
  const getSessionStyle = (session) => {
    const startDate = new Date(session.startTime)
    const endDate = session.endTime ? new Date(session.endTime) : new Date()

    const startMinutes = startDate.getHours() * 60 + startDate.getMinutes()
    const endMinutes = endDate.getHours() * 60 + endDate.getMinutes()
    const duration = endMinutes - startMinutes

    // Calculate percentage positions
    const left = (startMinutes / (24 * 60)) * 100
    const width = Math.max((duration / (24 * 60)) * 100, 1) // Minimum 1% width

    return {
      left: `${left}%`,
      width: `${width}%`,
      backgroundColor: STATUS_COLORS[session.status] || STATUS_COLORS.in_progress,
    }
  }

  const handleMouseEnter = (session, event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    setTooltipPosition({
      x: rect.left + rect.width / 2,
      y: rect.top - 10,
    })
    setHoveredSession(session)
  }

  const handleMouseLeave = () => {
    setHoveredSession(null)
  }

  const navigateDate = (direction) => {
    const newDate = new Date(selectedDate)
    newDate.setDate(newDate.getDate() + direction)
    onDateChange?.(newDate)
  }

  const formatDuration = (startTime, endTime) => {
    const start = new Date(startTime)
    const end = endTime ? new Date(endTime) : new Date()
    const diffMs = end - start
    const hours = Math.floor(diffMs / 3600000)
    const mins = Math.floor((diffMs % 3600000) / 60000)

    if (hours > 0) {
      return `${hours}h ${mins}m`
    }
    return `${mins}m`
  }

  const isToday = useMemo(() => {
    const today = new Date()
    return (
      selectedDate.getDate() === today.getDate() &&
      selectedDate.getMonth() === today.getMonth() &&
      selectedDate.getFullYear() === today.getFullYear()
    )
  }, [selectedDate])

  // Calculate summary stats
  const stats = useMemo(() => {
    const totalSessions = daySessions.length
    const successCount = daySessions.filter(s => s.status === 'success').length
    const failedCount = daySessions.filter(s => s.status === 'failed').length
    const inProgressCount = daySessions.filter(s => s.status === 'in_progress').length
    const totalTasks = daySessions.reduce((sum, s) => sum + (s.tasksCompleted || 0), 0)
    const totalTokens = daySessions.reduce((sum, s) => sum + (s.tokensUsed || 0), 0)

    return { totalSessions, successCount, failedCount, inProgressCount, totalTasks, totalTokens }
  }, [daySessions])

  return (
    <div
      className="rounded-xl p-4 md:p-6 border"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-2">
          <Calendar className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
          <h3
            className="font-semibold"
            style={{ color: 'var(--color-text)' }}
          >
            Session Timeline
          </h3>
        </div>

        {/* Date Navigation */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => navigateDate(-1)}
            className="p-1.5 rounded-lg transition-colors"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-textSecondary)',
            }}
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <div
            className="px-3 py-1.5 rounded-lg text-sm font-medium"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-text)',
            }}
          >
            {isToday ? 'Today' : selectedDate.toLocaleDateString(undefined, {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
            })}
          </div>

          <button
            onClick={() => navigateDate(1)}
            disabled={isToday}
            className="p-1.5 rounded-lg transition-colors disabled:opacity-50"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-textSecondary)',
            }}
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <div
          className="p-3 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <p
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Sessions
          </p>
          <p
            className="text-lg font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            {stats.totalSessions}
          </p>
        </div>

        <div
          className="p-3 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <p
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Success Rate
          </p>
          <p
            className="text-lg font-bold"
            style={{ color: stats.totalSessions > 0 ? '#22c55e' : 'var(--color-text)' }}
          >
            {stats.totalSessions > 0
              ? Math.round((stats.successCount / stats.totalSessions) * 100)
              : 0}%
          </p>
        </div>

        <div
          className="p-3 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <p
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Tasks Done
          </p>
          <p
            className="text-lg font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            {stats.totalTasks}
          </p>
        </div>

        <div
          className="p-3 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <p
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Tokens Used
          </p>
          <p
            className="text-lg font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            {stats.totalTokens > 1000
              ? `${(stats.totalTokens / 1000).toFixed(1)}K`
              : stats.totalTokens}
          </p>
        </div>
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Hour Labels */}
        <div className="flex justify-between mb-1">
          {[0, 6, 12, 18, 24].map(hour => (
            <span
              key={hour}
              className="text-xs"
              style={{ color: 'var(--color-textMuted)' }}
            >
              {hour === 24 ? '24:00' : `${hour.toString().padStart(2, '0')}:00`}
            </span>
          ))}
        </div>

        {/* Timeline Track */}
        <div
          className="relative h-16 rounded-lg overflow-hidden"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          {/* Hour grid lines */}
          {hours.map(hour => (
            <div
              key={hour}
              className="absolute top-0 bottom-0 w-px"
              style={{
                left: `${(hour / 24) * 100}%`,
                backgroundColor: 'var(--color-border)',
                opacity: hour % 6 === 0 ? 0.5 : 0.2,
              }}
            />
          ))}

          {/* Current time indicator (if today) */}
          {isToday && (
            <div
              className="absolute top-0 bottom-0 w-0.5 z-10"
              style={{
                left: `${((new Date().getHours() * 60 + new Date().getMinutes()) / (24 * 60)) * 100}%`,
                backgroundColor: '#ef4444',
              }}
            >
              <div
                className="absolute -top-1 -left-1 w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: '#ef4444' }}
              />
            </div>
          )}

          {/* Session Blocks */}
          {daySessions.map((session, index) => {
            const style = getSessionStyle(session)
            const StatusIcon = session.status === 'success'
              ? CheckCircle
              : session.status === 'failed'
              ? XCircle
              : session.status === 'in_progress'
              ? Loader2
              : Clock

            return (
              <div
                key={session.id || index}
                className="absolute top-2 bottom-2 rounded-md cursor-pointer transition-all hover:ring-2 hover:ring-white hover:ring-opacity-50"
                style={style}
                onMouseEnter={(e) => handleMouseEnter(session, e)}
                onMouseLeave={handleMouseLeave}
              >
                {/* Session content (if wide enough) */}
                <div className="h-full flex items-center justify-center overflow-hidden px-1">
                  <StatusIcon
                    className={`w-4 h-4 text-white ${session.status === 'in_progress' ? 'animate-spin' : ''}`}
                  />
                </div>
              </div>
            )
          })}

          {/* Empty state */}
          {daySessions.length === 0 && (
            <div
              className="absolute inset-0 flex items-center justify-center"
              style={{ color: 'var(--color-textMuted)' }}
            >
              <span className="text-sm">No sessions for this day</span>
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center gap-4 mt-4">
          {Object.entries(STATUS_COLORS).map(([status, color]) => (
            <div key={status} className="flex items-center gap-1">
              <div
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: color }}
              />
              <span
                className="text-xs capitalize"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                {status.replace('_', ' ')}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Tooltip */}
      {hoveredSession && (
        <div
          className="fixed z-50 p-3 rounded-lg shadow-lg max-w-xs"
          style={{
            left: tooltipPosition.x,
            top: tooltipPosition.y,
            transform: 'translate(-50%, -100%)',
            backgroundColor: 'var(--color-bgSecondary)',
            borderColor: 'var(--color-border)',
            border: '1px solid',
          }}
        >
          <div className="flex items-center justify-between mb-2">
            <span
              className="font-semibold text-sm"
              style={{ color: 'var(--color-text)' }}
            >
              Session #{hoveredSession.sessionNumber || hoveredSession.id}
            </span>
            <span
              className="text-xs px-2 py-0.5 rounded capitalize"
              style={{
                backgroundColor: `${STATUS_COLORS[hoveredSession.status]}20`,
                color: STATUS_COLORS[hoveredSession.status],
              }}
            >
              {hoveredSession.status?.replace('_', ' ')}
            </span>
          </div>

          <div
            className="space-y-1 text-xs"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            <div className="flex justify-between">
              <span>Duration:</span>
              <span style={{ color: 'var(--color-text)' }}>
                {formatDuration(hoveredSession.startTime, hoveredSession.endTime)}
              </span>
            </div>

            {hoveredSession.tasksCompleted !== undefined && (
              <div className="flex justify-between">
                <span>Tasks:</span>
                <span style={{ color: 'var(--color-text)' }}>
                  {hoveredSession.tasksCompleted} completed
                </span>
              </div>
            )}

            {hoveredSession.tokensUsed !== undefined && (
              <div className="flex justify-between">
                <span>Tokens:</span>
                <span style={{ color: 'var(--color-text)' }}>
                  {hoveredSession.tokensUsed.toLocaleString()}
                </span>
              </div>
            )}

            {hoveredSession.currentTask && (
              <div className="flex justify-between">
                <span>Current:</span>
                <span style={{ color: 'var(--color-accent)' }}>
                  {hoveredSession.currentTask}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default SessionTimeline
