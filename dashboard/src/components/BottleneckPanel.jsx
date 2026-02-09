import React from 'react'
import { AlertTriangle, Clock, RefreshCw, Lightbulb } from 'lucide-react'

function BottleneckPanel({ data }) {
  if (!data) return null

  const { stuck_tasks, avg_retry_rate, time_distribution, recommendations, longest_stuck } = data

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-white">Обнаружение узких мест</h3>
          <p className="text-sm text-gray-400">Автоматический анализ производительности</p>
        </div>
        {stuck_tasks.length > 0 && (
          <div className="flex items-center space-x-2 bg-yellow-500/10 text-yellow-500 px-3 py-1 rounded-full">
            <AlertTriangle className="w-4 h-4" />
            <span className="text-sm font-medium">{stuck_tasks.length} застряло</span>
          </div>
        )}
      </div>

      {/* Longest Stuck Task */}
      {longest_stuck && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
          <div className="flex items-start space-x-3">
            <Clock className="w-5 h-5 text-red-500 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-400">Самая застрявшая задача</p>
              <p className="text-white font-semibold">{longest_stuck.identifier}</p>
              <p className="text-sm text-gray-400">{longest_stuck.title}</p>
              <p className="text-sm text-red-400 mt-1">
                Застряла на {longest_stuck.hours_stuck}ч в статусе В работе
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Time Distribution */}
      <div className="mb-6">
        <h4 className="text-sm font-medium text-gray-400 mb-3">Среднее время в статусе</h4>
        <div className="space-y-2">
          {Object.entries(time_distribution).map(([state, hours]) => (
            <div key={state} className="flex items-center justify-between">
              <span className="text-sm text-gray-300">{state}</span>
              <div className="flex items-center space-x-2">
                <div className="w-32 h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full"
                    style={{ width: `${Math.min((hours / 10) * 100, 100)}%` }}
                  />
                </div>
                <span className="text-sm text-gray-400 w-12 text-right">{hours}h</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Retry Rate */}
      <div className="flex items-center justify-between bg-gray-700/50 rounded-lg p-3 mb-6">
        <div className="flex items-center space-x-3">
          <RefreshCw className="w-5 h-5 text-blue-500" />
          <span className="text-sm text-gray-300">Средняя частота повторов</span>
        </div>
        <span className="text-lg font-bold text-white">{avg_retry_rate}x</span>
      </div>

      {/* Recommendations */}
      <div>
        <h4 className="text-sm font-medium text-gray-400 mb-3 flex items-center space-x-2">
          <Lightbulb className="w-4 h-4 text-yellow-500" />
          <span>Рекомендации</span>
        </h4>
        <ul className="space-y-2">
          {recommendations.map((rec, index) => (
            <li
              key={index}
              className="text-sm text-gray-300 bg-gray-700/30 rounded-lg p-3 border-l-2 border-blue-500"
            >
              {rec}
            </li>
          ))}
        </ul>
      </div>

      {/* Stuck Tasks List */}
      {stuck_tasks.length > 0 && (
        <div className="mt-6">
          <h4 className="text-sm font-medium text-gray-400 mb-3">Застрявшие задачи</h4>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {stuck_tasks.map((task) => (
              <div
                key={task.identifier}
                className="flex items-center justify-between bg-gray-700/50 rounded-lg p-3"
              >
                <div>
                  <span className="text-sm font-medium text-white">{task.identifier}</span>
                  <p className="text-xs text-gray-400 truncate max-w-xs">{task.title}</p>
                </div>
                <div className="flex items-center space-x-2">
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      task.priority === 'urgent'
                        ? 'bg-red-500/20 text-red-400'
                        : task.priority === 'high'
                        ? 'bg-orange-500/20 text-orange-400'
                        : 'bg-gray-600/50 text-gray-400'
                    }`}
                  >
                    {task.priority}
                  </span>
                  <span className="text-sm text-yellow-500">{task.hours_stuck}h</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default BottleneckPanel
