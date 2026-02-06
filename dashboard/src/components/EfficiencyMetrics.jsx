import React from 'react'
import { CheckCircle, XCircle, Clock, PlayCircle, ListTodo } from 'lucide-react'

function MetricCard({ icon: Icon, label, value, subValue, color = 'blue' }) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    green: 'bg-green-500/10 text-green-500 border-green-500/20',
    red: 'bg-red-500/10 text-red-500 border-red-500/20',
    yellow: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
    purple: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
  }

  return (
    <div className={`rounded-xl p-4 border ${colorClasses[color]}`}>
      <div className="flex items-center space-x-3">
        <div className={`p-2 rounded-lg ${colorClasses[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="text-sm text-gray-400">{label}</p>
          <p className="text-xl font-bold text-white">{value}</p>
          {subValue && <p className="text-xs text-gray-500">{subValue}</p>}
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
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-white">Efficiency Metrics</h3>
        <p className="text-sm text-gray-400">Overall performance indicators</p>
      </div>

      {/* Success Rate Progress Bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-400">Success Rate</span>
          <span className="text-lg font-bold text-white">{success_rate}%</span>
        </div>
        <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-green-500 to-green-400 rounded-full transition-all duration-500"
            style={{ width: `${success_rate}%` }}
          />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-xs text-gray-500">Done: {tasks_done}</span>
          <span className="text-xs text-gray-500">Cancelled: {tasks_cancelled}</span>
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
