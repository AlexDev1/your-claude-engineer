import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Custom hook for Server-Sent Events (SSE) connection with automatic reconnection.
 *
 * @param {string} url - SSE endpoint URL
 * @param {Object} options - Configuration options
 * @param {boolean} options.enabled - Whether to connect (default: true)
 * @param {number} options.reconnectDelay - Delay before reconnecting in ms (default: 3000)
 * @param {number} options.maxRetries - Maximum reconnection attempts (default: 5)
 * @param {function} options.onMessage - Callback for incoming messages
 * @param {function} options.onError - Callback for errors
 * @param {function} options.onOpen - Callback when connection opens
 */
export function useSSE(url, options = {}) {
  const {
    enabled = true,
    reconnectDelay = 3000,
    maxRetries = 5,
    onMessage,
    onError,
    onOpen,
  } = options

  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const [retryCount, setRetryCount] = useState(0)
  const [lastEvent, setLastEvent] = useState(null)

  const eventSourceRef = useRef(null)
  const retryTimeoutRef = useRef(null)

  const connect = useCallback(() => {
    if (!enabled || !url) return

    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    try {
      const eventSource = new EventSource(url)
      eventSourceRef.current = eventSource

      eventSource.onopen = () => {
        setConnected(true)
        setError(null)
        setRetryCount(0)
        onOpen?.()
      }

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setLastEvent(data)
          onMessage?.(data)
        } catch (parseError) {
          // Handle non-JSON messages
          setLastEvent({ raw: event.data })
          onMessage?.({ raw: event.data })
        }
      }

      eventSource.onerror = (err) => {
        setConnected(false)
        setError('Connection lost')
        onError?.(err)

        eventSource.close()

        // Attempt reconnection
        if (retryCount < maxRetries) {
          retryTimeoutRef.current = setTimeout(() => {
            setRetryCount(prev => prev + 1)
            connect()
          }, reconnectDelay * Math.pow(2, retryCount)) // Exponential backoff
        }
      }

      // Handle custom event types
      eventSource.addEventListener('session', (event) => {
        try {
          const data = JSON.parse(event.data)
          setLastEvent({ type: 'session', ...data })
          onMessage?.({ type: 'session', ...data })
        } catch (e) {
          console.error('Failed to parse session event:', e)
        }
      })

      eventSource.addEventListener('activity', (event) => {
        try {
          const data = JSON.parse(event.data)
          setLastEvent({ type: 'activity', ...data })
          onMessage?.({ type: 'activity', ...data })
        } catch (e) {
          console.error('Failed to parse activity event:', e)
        }
      })

      eventSource.addEventListener('progress', (event) => {
        try {
          const data = JSON.parse(event.data)
          setLastEvent({ type: 'progress', ...data })
          onMessage?.({ type: 'progress', ...data })
        } catch (e) {
          console.error('Failed to parse progress event:', e)
        }
      })

      eventSource.addEventListener('notification', (event) => {
        try {
          const data = JSON.parse(event.data)
          setLastEvent({ type: 'notification', ...data })
          onMessage?.({ type: 'notification', ...data })
        } catch (e) {
          console.error('Failed to parse notification event:', e)
        }
      })

    } catch (err) {
      setError(err.message)
      onError?.(err)
    }
  }, [url, enabled, reconnectDelay, maxRetries, retryCount, onMessage, onError, onOpen])

  const disconnect = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setConnected(false)
    setRetryCount(0)
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [url, enabled]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    connected,
    error,
    retryCount,
    lastEvent,
    reconnect: connect,
    disconnect,
  }
}

/**
 * Hook for managing real-time session state with SSE
 */
export function useSessionLive(baseUrl = '') {
  const [session, setSession] = useState(null)
  const [activities, setActivities] = useState([])
  const [progress, setProgress] = useState({
    currentTask: null,
    stage: 'idle',
    percentage: 0,
    elapsedTime: 0,
    estimatedCompletion: null,
  })
  const [notifications, setNotifications] = useState([])

  const maxActivities = 50

  const handleMessage = useCallback((data) => {
    switch (data.type) {
      case 'session':
        setSession(data)
        break

      case 'activity':
        setActivities(prev => {
          const updated = [data, ...prev].slice(0, maxActivities)
          return updated
        })
        break

      case 'progress':
        setProgress(prev => ({
          ...prev,
          ...data,
        }))
        break

      case 'notification':
        setNotifications(prev => [data, ...prev].slice(0, 10))
        break

      default:
        // Handle generic message
        if (data.session) setSession(data.session)
        if (data.activities) setActivities(data.activities.slice(0, maxActivities))
        if (data.progress) setProgress(prev => ({ ...prev, ...data.progress }))
        break
    }
  }, [])

  const { connected, error, retryCount, reconnect, disconnect } = useSSE(
    `${baseUrl}/api/session/live`,
    {
      enabled: true,
      onMessage: handleMessage,
    }
  )

  const dismissNotification = useCallback((id) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
  }, [])

  const clearActivities = useCallback(() => {
    setActivities([])
  }, [])

  return {
    // Connection state
    connected,
    error,
    retryCount,
    reconnect,
    disconnect,

    // Session data
    session,
    activities,
    progress,
    notifications,

    // Actions
    dismissNotification,
    clearActivities,
  }
}

export default useSSE
