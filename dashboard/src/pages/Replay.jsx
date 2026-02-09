import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search,
  Filter,
  RefreshCw,
  Play,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Hash,
  Calendar,
} from 'lucide-react'
import { useSessions } from '../hooks/useSessions'

/** Map session status values to display colors */
const STATUS_COLORS = {
  completed: '#22c55e',
  failed: '#ef4444',
  running: '#3b82f6',
  unknown: '#6b7280',
}

/** Map session status values to icons */
const STATUS_ICONS = {
  completed: CheckCircle,
  failed: XCircle,
  running: Loader2,
  unknown: Clock,
}

/** Available status filter options */
const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'running', label: 'Running' },
]

/**
 * Format a duration in seconds to a human-readable string.
 *
 * @param {number|null} seconds - Duration in seconds
 * @returns {string} Formatted duration (e.g. "2h 15m" or "45m")
 */
function formatDuration(seconds) {
  if (seconds == null) return 'In progress'
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (hours > 0) return `${hours}h ${mins}m`
  if (mins > 0) return `${mins}m`
  return `${Math.round(seconds)}s`
}

/**
 * Format an ISO timestamp to a localized, human-readable string.
 *
 * @param {string} iso - ISO 8601 timestamp
 * @returns {string} Formatted date/time
 */
function formatTimestamp(iso) {
  if (!iso) return 'N/A'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/**
 * StatusBadge renders a colored pill showing the session status.
 *
 * @param {Object} props
 * @param {string} props.status - Session status string
 */
function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || STATUS_COLORS.unknown
  const Icon = STATUS_ICONS[status] || STATUS_ICONS.unknown
  const isRunning = status === 'running'

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium capitalize"
      style={{
        backgroundColor: `${color}18`,
        color,
      }}
    >
      <Icon className={`w-3 h-3 ${isRunning ? 'animate-spin' : ''}`} />
      {status}
    </span>
  )
}

/**
 * SessionCard renders a single session summary as a clickable card.
 *
 * @param {Object} props
 * @param {Object} props.session - Session summary object
 * @param {function} props.onClick - Callback when card is clicked
 */
function SessionCard({ session, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl p-4 border transition-all duration-200 hover:shadow-md"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--color-accent)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--color-cardBorder)'
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className="flex items-center justify-center w-8 h-8 rounded-lg"
            style={{ backgroundColor: 'var(--color-bgTertiary)' }}
          >
            <Hash className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
          </div>
          <div>
            <h3
              className="font-semibold text-sm"
              style={{ color: 'var(--color-text)' }}
            >
              Session #{session.id}
            </h3>
            {session.issue_id && (
              <span
                className="text-xs"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                {session.issue_id}
              </span>
            )}
          </div>
        </div>
        <StatusBadge status={session.status} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <p
            className="text-xs mb-0.5"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Started
          </p>
          <p
            className="text-sm font-medium"
            style={{ color: 'var(--color-text)' }}
          >
            {formatTimestamp(session.started_at)}
          </p>
        </div>
        <div>
          <p
            className="text-xs mb-0.5"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Duration
          </p>
          <p
            className="text-sm font-medium"
            style={{ color: 'var(--color-text)' }}
          >
            {formatDuration(session.duration_seconds)}
          </p>
        </div>
        <div>
          <p
            className="text-xs mb-0.5"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Events
          </p>
          <p
            className="text-sm font-medium"
            style={{ color: 'var(--color-text)' }}
          >
            {session.events_count}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-end mt-3">
        <span
          className="inline-flex items-center gap-1 text-xs font-medium"
          style={{ color: 'var(--color-accent)' }}
        >
          <Play className="w-3 h-3" />
          View Replay
        </span>
      </div>
    </button>
  )
}

/**
 * Replay page component showing a searchable, filterable list of recorded sessions.
 * Navigates to /replay/:id when a session card is clicked.
 */
function Replay() {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { sessions, total, loading, error, refetch } = useSessions({
    status: statusFilter || null,
    issueId: searchQuery || null,
  })

  /** Sessions with client-side search applied on top of API filter */
  const displayedSessions = useMemo(() => {
    if (!searchQuery) return sessions
    const query = searchQuery.toLowerCase()
    return sessions.filter(
      (s) =>
        s.issue_id?.toLowerCase().includes(query) ||
        String(s.id).includes(query),
    )
  }, [sessions, searchQuery])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2
            className="text-2xl font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            Session Replay
          </h2>
          <p
            className="mt-1"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Browse and replay recorded agent sessions
          </p>
        </div>

        <button
          onClick={refetch}
          disabled={loading}
          className="self-start flex items-center gap-2 px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            color: 'var(--color-textSecondary)',
          }}
          title="Refresh sessions"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          <span className="text-sm">Refresh</span>
        </button>
      </div>

      {/* Filters */}
      <div
        className="flex flex-col sm:flex-row gap-3 p-4 rounded-xl border"
        style={{
          backgroundColor: 'var(--color-cardBg)',
          borderColor: 'var(--color-cardBorder)',
        }}
      >
        {/* Search by Issue ID */}
        <div className="relative flex-1">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: 'var(--color-textMuted)' }}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by issue ID (e.g. ENG-74)..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg text-sm border transition-colors focus:outline-none"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = 'var(--color-accent)'
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = 'var(--color-border)'
            }}
          />
        </div>

        {/* Status Filter */}
        <div className="relative">
          <Filter
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: 'var(--color-textMuted)' }}
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="pl-10 pr-8 py-2.5 rounded-lg text-sm border appearance-none cursor-pointer transition-colors focus:outline-none"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
              minWidth: '160px',
            }}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Stats Bar */}
      <div
        className="flex items-center gap-6 text-sm"
        style={{ color: 'var(--color-textSecondary)' }}
      >
        <span className="flex items-center gap-1.5">
          <Calendar className="w-4 h-4" />
          {total} session{total !== 1 ? 's' : ''} found
        </span>
        {searchQuery && (
          <span>
            Filtering: <strong style={{ color: 'var(--color-text)' }}>{searchQuery}</strong>
          </span>
        )}
        {statusFilter && (
          <span>
            Status: <strong style={{ color: 'var(--color-text)' }}>{statusFilter}</strong>
          </span>
        )}
      </div>

      {/* Error State */}
      {error && (
        <div
          className="rounded-lg p-4 border"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171',
          }}
        >
          <p className="font-medium">Error loading sessions</p>
          <p className="text-sm mt-1">{error}</p>
          <p
            className="text-sm mt-2"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Showing demo data instead.
          </p>
        </div>
      )}

      {/* Loading State */}
      {loading && sessions.length === 0 && (
        <div className="flex items-center justify-center h-48">
          <div
            className="flex items-center space-x-3"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            <RefreshCw className="w-6 h-6 animate-spin" />
            <span>Loading sessions...</span>
          </div>
        </div>
      )}

      {/* Sessions Grid */}
      {displayedSessions.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {displayedSessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              onClick={() => navigate(`/replay/${session.id}`)}
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && displayedSessions.length === 0 && (
        <div
          className="flex flex-col items-center justify-center h-48 rounded-xl border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-cardBorder)',
          }}
        >
          <Clock
            className="w-10 h-10 mb-3"
            style={{ color: 'var(--color-textMuted)' }}
          />
          <p
            className="text-sm font-medium"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            No sessions found
          </p>
          <p
            className="text-xs mt-1"
            style={{ color: 'var(--color-textMuted)' }}
          >
            {searchQuery || statusFilter
              ? 'Try adjusting your filters'
              : 'Sessions will appear here after agent runs'}
          </p>
        </div>
      )}
    </div>
  )
}

export default Replay
