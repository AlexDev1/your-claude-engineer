import React from 'react'
import { Activity, CheckCircle, Clock, AlertTriangle } from 'lucide-react'

function MobileStatusSummary({ issues = [], onQuickAction }) {
  // Calculate summary stats
  const inProgress = issues.filter(i => i.state === 'In Progress')
  const todo = issues.filter(i => i.state === 'Todo')
  const done = issues.filter(i => i.state === 'Done')
  const urgent = issues.filter(i => i.priority === 'urgent' && i.state !== 'Done')

  const currentTask = inProgress[0] || todo[0]
  const completionRate = issues.length > 0
    ? Math.round((done.length / issues.length) * 100)
    : 0

  // Simulated recent actions
  const recentActions = [
    { icon: CheckCircle, text: 'Завершено ENG-42', time: '2 мин. назад', color: '#22c55e' },
    { icon: Activity, text: 'Начато ENG-43', time: '5 мин. назад', color: '#3b82f6' },
    { icon: Clock, text: 'Обновлён приоритет', time: '10 мин. назад', color: '#eab308' },
  ]

  return (
    <div className="mobile-status-summary">
      {/* Current Task */}
      <div>
        <div
          className="text-xs font-medium uppercase tracking-wider mb-2"
          style={{ color: 'var(--color-textMuted)' }}
        >
          Текущая задача
        </div>
        {currentTask ? (
          <div className="current-task">
            <span style={{ color: 'var(--color-textSecondary)' }}>
              {currentTask.identifier}
            </span>
            <span className="mx-2">-</span>
            <span>{currentTask.title}</span>
          </div>
        ) : (
          <div style={{ color: 'var(--color-textMuted)' }}>Нет активных задач</div>
        )}
      </div>

      {/* Progress Bar */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-xs font-medium"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Общий прогресс
          </span>
          <span
            className="text-sm font-semibold"
            style={{ color: 'var(--color-accent)' }}
          >
            {completionRate}%
          </span>
        </div>
        <div className="progress-bar">
          <div
            className="progress-bar-fill"
            style={{ width: `${completionRate}%` }}
          />
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-2">
        <div
          className="text-center p-2 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <div
            className="text-lg font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            {todo.length}
          </div>
          <div
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            К выполнению
          </div>
        </div>
        <div
          className="text-center p-2 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <div
            className="text-lg font-bold"
            style={{ color: '#3b82f6' }}
          >
            {inProgress.length}
          </div>
          <div
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Активно
          </div>
        </div>
        <div
          className="text-center p-2 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <div
            className="text-lg font-bold"
            style={{ color: '#22c55e' }}
          >
            {done.length}
          </div>
          <div
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Готово
          </div>
        </div>
        <div
          className="text-center p-2 rounded-lg"
          style={{ backgroundColor: urgent.length > 0 ? 'rgba(239, 68, 68, 0.1)' : 'var(--color-bgTertiary)' }}
        >
          <div
            className="text-lg font-bold"
            style={{ color: urgent.length > 0 ? '#ef4444' : 'var(--color-text)' }}
          >
            {urgent.length}
          </div>
          <div
            className="text-xs"
            style={{ color: 'var(--color-textMuted)' }}
          >
            Срочно
          </div>
        </div>
      </div>

      {/* Recent Actions */}
      <div>
        <div
          className="text-xs font-medium uppercase tracking-wider mb-2"
          style={{ color: 'var(--color-textMuted)' }}
        >
          Последняя активность
        </div>
        <div className="recent-actions">
          {recentActions.map((action, index) => (
            <div key={index} className="recent-action">
              <action.icon className="w-4 h-4" style={{ color: action.color }} />
              <span className="flex-1">{action.text}</span>
              <span style={{ color: 'var(--color-textMuted)' }}>{action.time}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-3 gap-2 pt-2">
        <button
          onClick={() => onQuickAction?.('pause')}
          className="flex items-center justify-center gap-2 py-3 rounded-lg transition-colors"
          style={{
            backgroundColor: 'var(--color-bgTertiary)',
            color: 'var(--color-text)'
          }}
        >
          <span className="text-sm font-medium">Пауза</span>
        </button>
        <button
          onClick={() => onQuickAction?.('skip')}
          className="flex items-center justify-center gap-2 py-3 rounded-lg transition-colors"
          style={{
            backgroundColor: 'var(--color-bgTertiary)',
            color: 'var(--color-text)'
          }}
        >
          <span className="text-sm font-medium">Пропустить</span>
        </button>
        <button
          onClick={() => onQuickAction?.('telegram')}
          className="flex items-center justify-center gap-2 py-3 rounded-lg transition-colors"
          style={{
            backgroundColor: 'var(--color-accent)',
            color: 'white'
          }}
        >
          <span className="text-sm font-medium">Сообщение</span>
        </button>
      </div>
    </div>
  )
}

export default MobileStatusSummary
