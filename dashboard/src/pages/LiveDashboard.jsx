import React, { useState, useEffect, useCallback } from 'react'
import { Radio, RefreshCw, Settings2, Wifi, WifiOff } from 'lucide-react'
import ProgressBar from '../components/ProgressBar'
import ActivityStream from '../components/ActivityStream'
import SessionTimeline from '../components/SessionTimeline'
import { ToastContainer, useToasts } from '../components/ToastNotifications'
import { useSessionLive } from '../hooks/useSSE'

/**
 * Generate demo data for development/testing
 */
function generateDemoData() {
  const now = new Date()

  // Demo activities
  const activities = [
    {
      id: '1',
      activityType: 'tool_call',
      title: 'Read file: src/App.jsx',
      description: 'Reading application entry point',
      timestamp: new Date(now - 5000).toISOString(),
      taskId: 'ENG-28',
    },
    {
      id: '2',
      activityType: 'file_change',
      title: 'Modified: components/ProgressBar.jsx',
      description: 'Added live progress tracking',
      timestamp: new Date(now - 30000).toISOString(),
      taskId: 'ENG-28',
      details: '+ 150 lines, - 10 lines',
    },
    {
      id: '3',
      activityType: 'test_result',
      title: 'Tests passed: 12/12',
      description: 'All unit tests passing',
      timestamp: new Date(now - 60000).toISOString(),
      taskId: 'ENG-28',
    },
    {
      id: '4',
      activityType: 'commit',
      title: 'Committed: feat(dashboard): add progress bar',
      description: 'ENG-28 implementation progress',
      timestamp: new Date(now - 120000).toISOString(),
      taskId: 'ENG-28',
    },
    {
      id: '5',
      activityType: 'task_complete',
      title: 'Completed: ENG-27',
      description: 'Session state management implemented',
      timestamp: new Date(now - 300000).toISOString(),
      taskId: 'ENG-27',
    },
    {
      id: '6',
      activityType: 'comment',
      title: 'Added comment on ENG-28',
      description: 'Updated progress notes',
      timestamp: new Date(now - 600000).toISOString(),
      taskId: 'ENG-28',
    },
    {
      id: '7',
      activityType: 'tool_call',
      title: 'Executed: npm run build',
      description: 'Production build check',
      timestamp: new Date(now - 900000).toISOString(),
    },
  ]

  // Demo sessions for timeline
  const sessions = [
    {
      id: 1,
      sessionNumber: 1,
      startTime: new Date(now.setHours(9, 0, 0, 0)).toISOString(),
      endTime: new Date(now.setHours(10, 30, 0, 0)).toISOString(),
      status: 'success',
      tasksCompleted: 3,
      tokensUsed: 45000,
    },
    {
      id: 2,
      sessionNumber: 2,
      startTime: new Date(now.setHours(11, 0, 0, 0)).toISOString(),
      endTime: new Date(now.setHours(12, 15, 0, 0)).toISOString(),
      status: 'success',
      tasksCompleted: 2,
      tokensUsed: 32000,
    },
    {
      id: 3,
      sessionNumber: 3,
      startTime: new Date(now.setHours(14, 0, 0, 0)).toISOString(),
      endTime: new Date(now.setHours(14, 45, 0, 0)).toISOString(),
      status: 'failed',
      tasksCompleted: 0,
      tokensUsed: 15000,
    },
    {
      id: 4,
      sessionNumber: 4,
      startTime: new Date(now.setHours(15, 0, 0, 0)).toISOString(),
      endTime: null, // In progress
      status: 'in_progress',
      tasksCompleted: 1,
      tokensUsed: 28000,
      currentTask: 'ENG-28',
    },
  ]

  // Demo progress
  const progress = {
    currentTask: 'ENG-28',
    stage: 'coding',
    percentage: 65,
    elapsedTime: 1800, // 30 minutes
    estimatedCompletion: new Date(Date.now() + 1800000).toISOString(), // 30 mins from now
  }

  return { activities, sessions, progress }
}

/**
 * Live Dashboard page - shows real-time session progress, activity stream, and timeline
 */
function LiveDashboard() {
  const [demoMode, setDemoMode] = useState(true) // Start in demo mode
  const [selectedDate, setSelectedDate] = useState(new Date())
  const [showSettings, setShowSettings] = useState(false)

  // Real SSE connection (disabled in demo mode)
  const {
    connected,
    error: sseError,
    retryCount,
    reconnect,
    disconnect,
    session,
    activities: liveActivities,
    progress: liveProgress,
    notifications,
    dismissNotification,
    clearActivities,
  } = useSessionLive(demoMode ? '' : '') // Would use actual API base URL

  // Demo data
  const [demoData, setDemoData] = useState(() => generateDemoData())

  // Toast notifications
  const { toasts, dismissToast, addToast } = useToasts()

  // Use demo data or live data
  const activities = demoMode ? demoData.activities : liveActivities
  const progress = demoMode ? demoData.progress : liveProgress
  const sessions = demoMode ? demoData.sessions : (session?.sessions || [])

  // Handle incoming notifications
  useEffect(() => {
    if (!demoMode) {
      notifications.forEach(notification => {
        addToast({
          id: notification.id,
          type: notification.notificationType || 'info',
          title: notification.title,
          message: notification.message,
          duration: notification.duration || 5000,
        })
        dismissNotification(notification.id)
      })
    }
  }, [notifications, demoMode, addToast, dismissNotification])

  // Simulate activity updates in demo mode
  useEffect(() => {
    if (!demoMode) return

    const activityTypes = ['tool_call', 'file_change', 'test_result', 'comment']
    const titles = [
      'Read file: src/utils/helpers.js',
      'Modified: components/Button.jsx',
      'Executed: npm test',
      'Added comment on current task',
      'Grep search: "useEffect"',
      'Write file: api/endpoint.js',
    ]

    const interval = setInterval(() => {
      const newActivity = {
        id: `demo-${Date.now()}`,
        activityType: activityTypes[Math.floor(Math.random() * activityTypes.length)],
        title: titles[Math.floor(Math.random() * titles.length)],
        timestamp: new Date().toISOString(),
        taskId: 'ENG-28',
      }

      setDemoData(prev => ({
        ...prev,
        activities: [newActivity, ...prev.activities].slice(0, 50),
        progress: {
          ...prev.progress,
          percentage: Math.min(100, prev.progress.percentage + Math.random() * 2),
          elapsedTime: prev.progress.elapsedTime + 5,
        },
      }))
    }, 5000)

    return () => clearInterval(interval)
  }, [demoMode])

  // Show demo notification periodically
  useEffect(() => {
    if (!demoMode) return

    const notificationTypes = [
      { type: 'task_complete', title: 'Task Completed', message: 'ENG-27 has been completed successfully' },
      { type: 'test_failed', title: 'Test Failed', message: 'Unit test failed in Button.test.jsx' },
      { type: 'info', title: 'Build Started', message: 'Production build initiated' },
    ]

    const timeout = setTimeout(() => {
      const notification = notificationTypes[Math.floor(Math.random() * notificationTypes.length)]
      addToast({
        ...notification,
        duration: 5000,
      })
    }, 10000)

    return () => clearTimeout(timeout)
  }, [demoMode, addToast, toasts])

  const handleClearActivities = useCallback(() => {
    if (demoMode) {
      setDemoData(prev => ({ ...prev, activities: [] }))
    } else {
      clearActivities()
    }
  }, [demoMode, clearActivities])

  const toggleDemoMode = () => {
    setDemoMode(prev => {
      if (prev) {
        // Switching to live mode
        reconnect()
      } else {
        // Switching to demo mode
        disconnect()
        setDemoData(generateDemoData())
      }
      return !prev
    })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div
            className={`p-2 rounded-lg ${!demoMode && connected ? 'animate-pulse' : ''}`}
            style={{
              backgroundColor: !demoMode && connected
                ? 'rgba(34, 197, 94, 0.1)'
                : 'var(--color-bgTertiary)',
            }}
          >
            <Radio
              className="w-6 h-6"
              style={{
                color: !demoMode && connected ? '#22c55e' : 'var(--color-accent)',
              }}
            />
          </div>
          <div>
            <h2
              className="text-2xl font-bold"
              style={{ color: 'var(--color-text)' }}
            >
              Live Dashboard
            </h2>
            <p
              className="mt-1 text-sm"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              {demoMode
                ? 'Demo mode - simulated data'
                : connected
                ? 'Real-time session monitoring'
                : 'Disconnected - click reconnect'}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Connection Status */}
          <div
            className="flex items-center space-x-2 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'var(--color-cardBg)' }}
          >
            {demoMode ? (
              <>
                <div className="w-2 h-2 rounded-full bg-yellow-500" />
                <span
                  className="text-sm"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  Demo
                </span>
              </>
            ) : connected ? (
              <>
                <Wifi className="w-4 h-4 text-green-500" />
                <span
                  className="text-sm"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  Connected
                </span>
              </>
            ) : (
              <>
                <WifiOff className="w-4 h-4 text-red-500" />
                <span
                  className="text-sm"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  {retryCount > 0 ? `Retry ${retryCount}...` : 'Disconnected'}
                </span>
              </>
            )}
          </div>

          {/* Mode Toggle */}
          <button
            onClick={toggleDemoMode}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              backgroundColor: demoMode ? 'var(--color-accent)' : 'var(--color-cardBg)',
              color: demoMode ? 'white' : 'var(--color-textSecondary)',
            }}
          >
            {demoMode ? 'Switch to Live' : 'Demo Mode'}
          </button>

          {/* Refresh / Reconnect */}
          {!demoMode && !connected && (
            <button
              onClick={reconnect}
              className="p-2 rounded-lg transition-colors"
              style={{
                backgroundColor: 'var(--color-cardBg)',
                color: 'var(--color-textSecondary)',
              }}
              title="Reconnect"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
          )}

          {/* Settings */}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 rounded-lg transition-colors"
            style={{
              backgroundColor: showSettings ? 'var(--color-bgTertiary)' : 'var(--color-cardBg)',
              color: 'var(--color-textSecondary)',
            }}
            title="Settings"
          >
            <Settings2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* SSE Error */}
      {sseError && !demoMode && (
        <div
          className="rounded-lg p-4 border"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171',
          }}
        >
          <p className="font-medium">Connection Error</p>
          <p className="text-sm mt-1">{sseError}</p>
          <button
            onClick={reconnect}
            className="mt-2 text-sm font-medium underline"
          >
            Try reconnecting
          </button>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Progress + Timeline */}
        <div className="lg:col-span-2 space-y-6">
          {/* Progress Bar */}
          <ProgressBar
            progress={progress}
            connected={demoMode || connected}
            onReconnect={reconnect}
          />

          {/* Session Timeline */}
          <SessionTimeline
            sessions={sessions}
            selectedDate={selectedDate}
            onDateChange={setSelectedDate}
          />
        </div>

        {/* Right Column - Activity Stream */}
        <div className="lg:col-span-1">
          <ActivityStream
            activities={activities}
            onClear={handleClearActivities}
            maxItems={50}
          />
        </div>
      </div>

      {/* Toast Notifications */}
      <ToastContainer
        toasts={toasts}
        onDismiss={dismissToast}
        position="top-right"
        maxToasts={5}
      />
    </div>
  )
}

export default LiveDashboard
