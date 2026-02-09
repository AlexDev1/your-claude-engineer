import { useState, useEffect, useCallback } from 'react'

const API_BASE = '/api/sessions'

/**
 * Generate mock session data for demo/development mode.
 *
 * @param {number} count - Number of mock sessions to generate
 * @returns {Array} Array of mock session summary objects
 */
function generateMockSessions(count = 12) {
  const statuses = ['completed', 'completed', 'completed', 'failed', 'running', 'completed']
  const issueIds = ['ENG-74', 'ENG-75', 'ENG-76', 'ENG-77', 'ENG-78', 'ENG-70', 'ENG-62']
  const sessions = []

  for (let i = count; i >= 1; i--) {
    const startDate = new Date()
    startDate.setHours(startDate.getHours() - (count - i) * 3)
    const status = statuses[i % statuses.length]
    const durationSeconds = status === 'running' ? null : 300 + (i * 137) % 3600
    const endDate = durationSeconds
      ? new Date(startDate.getTime() + durationSeconds * 1000)
      : null

    sessions.push({
      id: i,
      started_at: startDate.toISOString(),
      ended_at: endDate ? endDate.toISOString() : null,
      duration_seconds: durationSeconds,
      events_count: 5 + (i * 17) % 50,
      status,
      issue_id: issueIds[i % issueIds.length],
    })
  }

  return sessions
}

/**
 * Generate mock event data for a single session replay.
 *
 * @param {number} sessionId - The session ID to generate events for
 * @returns {Object} Full session object with events
 */
function generateMockSessionDetail(sessionId) {
  const eventTypes = ['tool_call', 'file_write', 'bash', 'agent_call']
  const toolNames = ['Read', 'Write', 'Edit', 'Bash', 'Grep', 'Glob']
  const filePaths = [
    'dashboard/src/App.jsx',
    'dashboard/src/pages/Replay.jsx',
    'analytics_server/server.py',
    'session_recorder.py',
    'dashboard/src/hooks/useSessions.js',
  ]

  const eventsCount = 10 + (sessionId * 7) % 30
  const events = []
  let currentTime = 0

  for (let i = 0; i < eventsCount; i++) {
    currentTime += 5 + Math.floor(Math.random() * 30)
    const type = eventTypes[i % eventTypes.length]

    const event = {
      t: currentTime,
      type,
      data: {},
    }

    if (type === 'tool_call') {
      const tool = toolNames[i % toolNames.length]
      event.data = {
        tool,
        arguments: { file_path: filePaths[i % filePaths.length] },
        result_preview: `Successfully executed ${tool} on ${filePaths[i % filePaths.length]}`,
      }
    } else if (type === 'file_write') {
      event.data = {
        file_path: filePaths[i % filePaths.length],
        old_content: `// Old content for line ${i}\nfunction oldVersion() {\n  return null\n}`,
        new_content: `// Updated content for line ${i}\nfunction newVersion() {\n  return { updated: true }\n}`,
      }
    } else if (type === 'bash') {
      event.data = {
        command: 'npm run build',
        output_preview: 'Build completed successfully in 3.2s',
        exit_code: 0,
      }
    } else if (type === 'agent_call') {
      event.data = {
        agent: 'sub-agent',
        prompt: 'Review the implementation',
        result_preview: 'Implementation looks good. No issues found.',
      }
    }

    events.push(event)
  }

  const startDate = new Date()
  startDate.setHours(startDate.getHours() - 2)
  const totalDuration = currentTime + 10

  return {
    session_id: sessionId,
    started_at: startDate.toISOString(),
    ended_at: new Date(startDate.getTime() + totalDuration * 1000).toISOString(),
    issue_id: `ENG-${70 + (sessionId % 10)}`,
    status: 'completed',
    events,
  }
}

/**
 * Hook for fetching session list with filtering and pagination.
 *
 * @param {Object} options
 * @param {string} options.status - Filter by status (null for all)
 * @param {string} options.issueId - Filter by issue ID (null for all)
 * @param {number} options.limit - Page size
 * @param {number} options.offset - Pagination offset
 * @returns {Object} { sessions, total, loading, error, refetch }
 */
export function useSessions({ status = null, issueId = null, limit = 50, offset = 0 } = {}) {
  const [sessions, setSessions] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchSessions = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const params = new URLSearchParams()
      params.set('limit', String(limit))
      params.set('offset', String(offset))
      if (status) params.set('status', status)
      if (issueId) params.set('issue_id', issueId)

      const response = await fetch(`${API_BASE}?${params.toString()}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch sessions: ${response.status}`)
      }

      const result = await response.json()
      setSessions(result.sessions || [])
      setTotal(result.total || 0)
    } catch (err) {
      setError(err.message)
      // Fall back to mock data in development
      const mockData = generateMockSessions()
      let filtered = mockData
      if (status) {
        filtered = filtered.filter((s) => s.status === status)
      }
      if (issueId) {
        filtered = filtered.filter((s) =>
          s.issue_id.toLowerCase().includes(issueId.toLowerCase()),
        )
      }
      setSessions(filtered)
      setTotal(filtered.length)
    } finally {
      setLoading(false)
    }
  }, [status, issueId, limit, offset])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  return { sessions, total, loading, error, refetch: fetchSessions }
}

/**
 * Hook for fetching a single session's full data (including events) for replay.
 *
 * @param {number|string} sessionId - The session ID to fetch
 * @returns {Object} { session, loading, error, refetch }
 */
export function useSessionDetail(sessionId) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchSession = useCallback(async () => {
    if (!sessionId) return

    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/${sessionId}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch session: ${response.status}`)
      }

      const result = await response.json()
      setSession(result)
    } catch (err) {
      setError(err.message)
      // Fall back to mock data in development
      setSession(generateMockSessionDetail(Number(sessionId)))
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    fetchSession()
  }, [fetchSession])

  return { session, loading, error, refetch: fetchSession }
}
