import React from 'react'
import { CheckCircle, XCircle, Clock, PlayCircle, ListTodo } from 'lucide-react'

function MetricCard({ icon: Icon, label, value, subValue, color = 'blue' }) {
  const colorClasses = {
    blue: { bg: 'rgba(96, 165, 250, 0.1)', text: '#60a5fa', border: 'rgba(96, 165, 250, 0.2)' },
    green: { bg: 'rgba(34, 197, 94, 0.1)', text: '#22c55e', border: 'rgba(34, 197, 94, 0.2)' },
    red: { bg: 'rgba(239, 68, 68, 0.1)', text: '#ef4444', border: 'rgba(239, 68, 68, 0.2)' },
    yellow: { bg: 'rgba(234, 179, 8, 0.1)', text: '#eab308', border: 'rgba(234, 179, 8, 0.2)' },
    purple: { bg: 'rgba(168, 85, 247, 0.1)', text: '#a855f7', border: 'rgba(168, 85, 247, 0.2)' },
  }

  const colors = colorClasses[color]

  return (
    <div
      className="rounded-xl p-4 border"
      style={{
        backgroundColor: colors.bg,
        borderColor: colors.border
      }}
    >
      <div className="flex items-center space-x-3">
        <div
          className="p-2 rounded-lg"
          style={{ backgroundColor: colors.bg }}
        >
          <Icon className="w-5 h-5" style={{ color: colors.text }} />
        </div>
        <div>
          <p
            className="text-sm"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            {label}
          </p>
          <p
            className="text-xl font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            {value}
          </p>
          {subValue && (
            <p
              className="text-xs"
              style={{ color: 'var(--color-textMuted)' }}
            >
              {subValue}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function EfficiencyMetrics({ data }) {
  if (!data) return null

  const {
    success_rate,
    avg_completion_time_hours,
    tasks_done,
    tasks_cancelled,
    tasks_in_progress,
    tasks_todo,
  } = data

  const formatTime = (hours) => {
    if (hours < 1) return `${Math.round(hours * 60)}m`
    if (hours < 24) return `${hours.toFixed(1)}h`
    return `${(hours / 24).toFixed(1)}d`
  }

  return (
    <div
      className="rounded-xl p-6 border"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)'
      }}
    >
      <div className="mb-6">
        <h3
          className="text-lg font-semibold"
          style={{ color: 'var(--color-text)' }}
        >
          Efficiency Metrics
        </h3>
        <p
          className="text-sm"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          Overall performance indicators
        </p>
      </div>

      {/* Success Rate Progress Bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-sm"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Success Rate
          </span>
          <span
            className="text-lg font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            {success_rate}%
          </span>
        </div>
        <div
          className="h-3 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${success_rate}%`,
              background: 'linear-gradient(to right, #22c55e, #4ade80)'
            }}
          />
        </div>
        <div className="flex justify-between mt-1">
          <span
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Done: {tasks_done}
          </span>
          <span
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Cancelled: {tasks_cancelled}
          </span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-4">
        <MetricCard
          icon={CheckCircle}
          label="Completed"
          value={tasks_done}
          subValue="tasks done"
          color="green"
        />
        <MetricCard
          icon={Clock}
          label="Avg. Time"
          value={formatTime(avg_completion_time_hours)}
          subValue="to complete"
          color="blue"
        />
        <MetricCard
          icon={PlayCircle}
          label="In Progress"
          value={tasks_in_progress}
          subValue="active tasks"
          color="yellow"
        />
        <MetricCard
          icon={ListTodo}
          label="Backlog"
          value={tasks_todo}
          subValue="in queue"
          color="purple"
        />
      </div>
    </div>
  )
}

export default EfficiencyMetrics
