import React, { useState, useRef, useEffect } from 'react'
import {
  Activity,
  FileCode,
  GitCommit,
  MessageSquare,
  CheckCircle,
  XCircle,
  TestTube,
  Wrench,
  Filter,
  Trash2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from 'lucide-react'

/**
 * Activity type configuration
 */
const ACTIVITY_TYPES = {
  tool_call: { icon: Wrench, color: '#8b5cf6', label: 'Tool Call' },
  file_change: { icon: FileCode, color: '#3b82f6', label: 'File Change' },
  test_result: { icon: TestTube, color: '#eab308', label: 'Test Result' },
  commit: { icon: GitCommit, color: '#22c55e', label: 'Commit' },
  comment: { icon: MessageSquare, color: '#06b6d4', label: 'Comment' },
  task_complete: { icon: CheckCircle, color: '#22c55e', label: 'Task Complete' },
  task_failed: { icon: XCircle, color: '#ef4444', label: 'Task Failed' },
  default: { icon: Activity, color: 'var(--color-accent)', label: 'Activity' },
}

/**
 * Activity Stream component showing recent agent actions
 *
 * @param {Object} props
 * @param {Array} props.activities - List of activity events
 * @param {function} props.onClear - Callback to clear activities
 * @param {number} props.maxItems - Maximum items to display (default: 50)
 */
function ActivityStream({ activities = [], onClear, maxItems = 50 }) {
  const [filter, setFilter] = useState('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [expandedItems, setExpandedItems] = useState(new Set())
  const [showFilters, setShowFilters] = useState(false)

  const streamRef = useRef(null)

  // Auto-scroll to top when new activities arrive
  useEffect(() => {
    if (autoScroll && streamRef.current) {
      streamRef.current.scrollTop = 0
    }
  }, [activities, autoScroll])

  const filteredActivities = activities
    .filter(activity => filter === 'all' || activity.activityType === filter)
    .slice(0, maxItems)

  const getActivityConfig = (type) => {
    return ACTIVITY_TYPES[type] || ACTIVITY_TYPES.default
  }

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Just now'

    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    return date.toLocaleDateString()
  }

  const toggleExpand = (id) => {
    setExpandedItems(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const uniqueTypes = [...new Set(activities.map(a => a.activityType).filter(Boolean))]

  return (
    <div
      className="rounded-xl border flex flex-col h-full min-h-[400px] max-h-[600px]"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between p-4 border-b"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <div className="flex items-center space-x-2">
          <Activity className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
          <h3
            className="font-semibold"
            style={{ color: 'var(--color-text)' }}
          >
            Activity Stream
          </h3>
          <span
            className="text-xs px-2 py-0.5 rounded-full"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-textSecondary)',
            }}
          >
            {filteredActivities.length}
          </span>
        </div>

        <div className="flex items-center space-x-2">
          {/* Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`p-2 rounded-lg transition-colors ${showFilters ? 'ring-1' : ''}`}
            style={{
              backgroundColor: showFilters ? 'var(--color-bgTertiary)' : 'transparent',
              color: 'var(--color-textSecondary)',
              ringColor: 'var(--color-accent)',
            }}
            title="Filter activities"
          >
            <Filter className="w-4 h-4" />
          </button>

          {/* Auto-scroll Toggle */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`p-2 rounded-lg transition-colors`}
            style={{
              backgroundColor: autoScroll ? 'rgba(34, 197, 94, 0.1)' : 'transparent',
              color: autoScroll ? '#22c55e' : 'var(--color-textSecondary)',
            }}
            title={autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
          >
            {autoScroll ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>

          {/* Clear Button */}
          {onClear && activities.length > 0 && (
            <button
              onClick={onClear}
              className="p-2 rounded-lg transition-colors"
              style={{
                backgroundColor: 'transparent',
                color: 'var(--color-textSecondary)',
              }}
              title="Clear activities"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Filter Bar */}
      {showFilters && (
        <div
          className="flex items-center gap-2 p-3 border-b overflow-x-auto"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1 text-xs rounded-full whitespace-nowrap transition-colors`}
            style={{
              backgroundColor: filter === 'all' ? 'var(--color-accent)' : 'var(--color-bgTertiary)',
              color: filter === 'all' ? 'white' : 'var(--color-textSecondary)',
            }}
          >
            All
          </button>
          {uniqueTypes.map(type => {
            const config = getActivityConfig(type)
            return (
              <button
                key={type}
                onClick={() => setFilter(type)}
                className={`flex items-center gap-1 px-3 py-1 text-xs rounded-full whitespace-nowrap transition-colors`}
                style={{
                  backgroundColor: filter === type ? config.color : 'var(--color-bgTertiary)',
                  color: filter === type ? 'white' : 'var(--color-textSecondary)',
                }}
              >
                <config.icon className="w-3 h-3" />
                {config.label}
              </button>
            )
          })}
        </div>
      )}

      {/* Activity List */}
      <div
        ref={streamRef}
        className="flex-1 overflow-y-auto p-4 space-y-3"
        style={{ scrollBehavior: 'smooth' }}
      >
        {filteredActivities.length === 0 ? (
          <div
            className="flex flex-col items-center justify-center h-full py-8"
            style={{ color: 'var(--color-textMuted)' }}
          >
            <Activity className="w-12 h-12 mb-2 opacity-50" />
            <p className="text-sm">No activities yet</p>
            <p className="text-xs mt-1">Activities will appear here in real-time</p>
          </div>
        ) : (
          filteredActivities.map((activity, index) => {
            const config = getActivityConfig(activity.activityType)
            const Icon = config.icon
            const isExpanded = expandedItems.has(activity.id || index)

            return (
              <div
                key={activity.id || index}
                className="group relative"
              >
                {/* Timeline connector */}
                {index < filteredActivities.length - 1 && (
                  <div
                    className="absolute left-5 top-10 bottom-0 w-px"
                    style={{ backgroundColor: 'var(--color-border)' }}
                  />
                )}

                <div
                  className="flex items-start space-x-3 p-3 rounded-lg transition-colors cursor-pointer"
                  style={{ backgroundColor: 'transparent' }}
                  onClick={() => activity.details && toggleExpand(activity.id || index)}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent'
                  }}
                >
                  {/* Icon */}
                  <div
                    className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center"
                    style={{ backgroundColor: `${config.color}20` }}
                  >
                    <Icon className="w-5 h-5" style={{ color: config.color }} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p
                        className="text-sm font-medium truncate"
                        style={{ color: 'var(--color-text)' }}
                      >
                        {activity.title || activity.message || config.label}
                      </p>
                      <span
                        className="text-xs flex-shrink-0 ml-2"
                        style={{ color: 'var(--color-textMuted)' }}
                      >
                        {formatTimestamp(activity.timestamp)}
                      </span>
                    </div>

                    {activity.description && (
                      <p
                        className="text-xs mt-1 truncate"
                        style={{ color: 'var(--color-textSecondary)' }}
                      >
                        {activity.description}
                      </p>
                    )}

                    {/* Task Reference */}
                    {activity.taskId && (
                      <span
                        className="inline-flex items-center gap-1 mt-1 text-xs px-2 py-0.5 rounded"
                        style={{
                          backgroundColor: 'var(--color-bgTertiary)',
                          color: 'var(--color-accent)',
                        }}
                      >
                        {activity.taskId}
                        <ExternalLink className="w-3 h-3" />
                      </span>
                    )}

                    {/* Expanded Details */}
                    {isExpanded && activity.details && (
                      <div
                        className="mt-2 p-2 rounded text-xs font-mono overflow-x-auto"
                        style={{
                          backgroundColor: 'var(--color-bg)',
                          color: 'var(--color-textSecondary)',
                        }}
                      >
                        <pre className="whitespace-pre-wrap">
                          {typeof activity.details === 'string'
                            ? activity.details
                            : JSON.stringify(activity.details, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>

                  {/* Expand indicator */}
                  {activity.details && (
                    <button
                      className="opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: 'var(--color-textMuted)' }}
                    >
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Footer with stats */}
      <div
        className="flex items-center justify-between px-4 py-2 border-t text-xs"
        style={{
          borderColor: 'var(--color-border)',
          color: 'var(--color-textMuted)',
        }}
      >
        <span>
          Showing {filteredActivities.length} of {activities.length} activities
        </span>
        <span>
          {autoScroll ? 'Auto-scroll enabled' : 'Scroll manually'}
        </span>
      </div>
    </div>
  )
}

export default ActivityStream
