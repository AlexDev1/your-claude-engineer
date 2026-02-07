import React, { useState, useEffect } from 'react'
import { Play, Pause, Clock, Zap, CheckCircle, Code, TestTube, GitCommit, Loader2 } from 'lucide-react'

/**
 * Stage configuration for the progress pipeline
 */
const STAGES = [
  { id: 'analysis', label: 'Analysis', icon: Zap, color: '#eab308' },
  { id: 'coding', label: 'Coding', icon: Code, color: '#3b82f6' },
  { id: 'testing', label: 'Testing', icon: TestTube, color: '#8b5cf6' },
  { id: 'commit', label: 'Commit', icon: GitCommit, color: '#22c55e' },
]

/**
 * Live Progress Bar component showing current session progress
 *
 * @param {Object} props
 * @param {Object} props.progress - Progress state from useSessionLive
 * @param {boolean} props.connected - SSE connection status
 * @param {function} props.onReconnect - Callback to reconnect SSE
 */
function ProgressBar({ progress = {}, connected = false, onReconnect }) {
  const {
    currentTask = null,
    stage = 'idle',
    percentage = 0,
    elapsedTime = 0,
    estimatedCompletion = null,
  } = progress

  const [displayTime, setDisplayTime] = useState(elapsedTime)

  // Update elapsed time every second when active
  useEffect(() => {
    if (stage === 'idle' || !currentTask) {
      setDisplayTime(0)
      return
    }

    setDisplayTime(elapsedTime)

    const interval = setInterval(() => {
      setDisplayTime(prev => prev + 1)
    }, 1000)

    return () => clearInterval(interval)
  }, [stage, currentTask, elapsedTime])

  const formatTime = (seconds) => {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60

    if (hours > 0) {
      return `${hours}h ${mins}m ${secs}s`
    } else if (mins > 0) {
      return `${mins}m ${secs}s`
    }
    return `${secs}s`
  }

  const getStageIndex = () => {
    return STAGES.findIndex(s => s.id === stage)
  }

  const currentStageIndex = getStageIndex()
  const isActive = stage !== 'idle' && currentTask

  return (
    <div
      className="rounded-xl p-4 md:p-6 border transition-all"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: isActive ? 'var(--color-accent)' : 'var(--color-cardBorder)',
        boxShadow: isActive ? '0 0 20px rgba(96, 165, 250, 0.1)' : 'none',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div
            className={`p-2 rounded-lg ${isActive ? 'animate-pulse' : ''}`}
            style={{
              backgroundColor: isActive ? 'rgba(96, 165, 250, 0.1)' : 'var(--color-bgTertiary)',
            }}
          >
            {isActive ? (
              <Play className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
            ) : (
              <Pause className="w-5 h-5" style={{ color: 'var(--color-textMuted)' }} />
            )}
          </div>
          <div>
            <h3
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text)' }}
            >
              {isActive ? 'Session Active' : 'Session Idle'}
            </h3>
            <p
              className="text-xs"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              {currentTask ? `Working on ${currentTask}` : 'No active task'}
            </p>
          </div>
        </div>

        {/* Connection Status */}
        <div className="flex items-center space-x-2">
          <div
            className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`}
            title={connected ? 'Connected' : 'Disconnected'}
          />
          {!connected && (
            <button
              onClick={onReconnect}
              className="text-xs px-2 py-1 rounded transition-colors"
              style={{
                backgroundColor: 'var(--color-bgTertiary)',
                color: 'var(--color-textSecondary)',
              }}
            >
              Reconnect
            </button>
          )}
        </div>
      </div>

      {/* Stage Pipeline */}
      <div className="relative mb-6">
        {/* Progress Track */}
        <div
          className="absolute top-5 left-0 right-0 h-1 rounded-full"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        />

        {/* Progress Fill */}
        <div
          className="absolute top-5 left-0 h-1 rounded-full transition-all duration-500"
          style={{
            backgroundColor: 'var(--color-accent)',
            width: isActive
              ? `${Math.max(0, Math.min(100, ((currentStageIndex + 1) / STAGES.length) * 100 * (percentage / 100)))}%`
              : '0%',
          }}
        />

        {/* Stage Nodes */}
        <div className="relative flex justify-between">
          {STAGES.map((stageItem, index) => {
            const Icon = stageItem.icon
            const isCompleted = currentStageIndex > index
            const isCurrent = stageItem.id === stage
            const isPending = currentStageIndex < index

            return (
              <div
                key={stageItem.id}
                className="flex flex-col items-center"
                style={{ width: `${100 / STAGES.length}%` }}
              >
                {/* Node Circle */}
                <div
                  className={`relative w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 ${
                    isCurrent ? 'ring-2 ring-offset-2' : ''
                  }`}
                  style={{
                    backgroundColor: isCompleted
                      ? '#22c55e'
                      : isCurrent
                      ? stageItem.color
                      : 'var(--color-bgTertiary)',
                    ringColor: isCurrent ? stageItem.color : 'transparent',
                    ringOffsetColor: 'var(--color-cardBg)',
                  }}
                >
                  {isCompleted ? (
                    <CheckCircle className="w-5 h-5 text-white" />
                  ) : isCurrent ? (
                    <Loader2 className="w-5 h-5 text-white animate-spin" />
                  ) : (
                    <Icon
                      className="w-5 h-5"
                      style={{ color: isPending ? 'var(--color-textMuted)' : 'white' }}
                    />
                  )}
                </div>

                {/* Label */}
                <span
                  className={`mt-2 text-xs font-medium ${isCurrent ? 'font-semibold' : ''}`}
                  style={{
                    color: isCurrent
                      ? stageItem.color
                      : isCompleted
                      ? 'var(--color-text)'
                      : 'var(--color-textMuted)',
                  }}
                >
                  {stageItem.label}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-xs font-medium"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Overall Progress
          </span>
          <span
            className="text-sm font-semibold"
            style={{ color: 'var(--color-accent)' }}
          >
            {Math.round(percentage)}%
          </span>
        </div>
        <div
          className="h-2 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${percentage}%`,
              backgroundColor: 'var(--color-accent)',
            }}
          />
        </div>
      </div>

      {/* Time Stats */}
      <div className="grid grid-cols-2 gap-4">
        <div
          className="flex items-center space-x-2 p-3 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <Clock className="w-4 h-4" style={{ color: 'var(--color-textMuted)' }} />
          <div>
            <p
              className="text-xs"
              style={{ color: 'var(--color-textMuted)' }}
            >
              Elapsed
            </p>
            <p
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text)' }}
            >
              {formatTime(displayTime)}
            </p>
          </div>
        </div>

        <div
          className="flex items-center space-x-2 p-3 rounded-lg"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
        >
          <Zap className="w-4 h-4" style={{ color: 'var(--color-textMuted)' }} />
          <div>
            <p
              className="text-xs"
              style={{ color: 'var(--color-textMuted)' }}
            >
              Est. Completion
            </p>
            <p
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text)' }}
            >
              {estimatedCompletion
                ? new Date(estimatedCompletion).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                : '--:--'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ProgressBar
