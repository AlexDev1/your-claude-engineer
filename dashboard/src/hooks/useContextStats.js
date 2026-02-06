import { useState, useEffect, useCallback } from 'react'

const API_BASE = '/api'

// Demo data for development when API is unavailable
function generateDemoStats() {
  const maxTokens = 200000
  const breakdown = {
    system_prompt: 2283,
    files: Math.floor(Math.random() * 40000) + 20000,
    history: Math.floor(Math.random() * 15000) + 5000,
    memory: 1500,
    issue: Math.floor(Math.random() * 2000) + 500,
  }
  const totalUsed = Object.values(breakdown).reduce((a, b) => a + b, 0)

  return {
    max_tokens: maxTokens,
    total_used: totalUsed,
    remaining: maxTokens - totalUsed,
    usage_percent: (totalUsed / maxTokens) * 100,
    is_warning: totalUsed >= maxTokens * 0.8,
    breakdown,
    files_loaded: Math.floor(Math.random() * 15) + 5,
    history_messages: Math.floor(Math.random() * 12) + 3,
    prompts: {
      orchestrator_prompt: { chars: 1858, tokens: 464 },
      coding_agent_prompt: { chars: 1604, tokens: 401 },
      task_agent_prompt: { chars: 1272, tokens: 318 },
      reviewer_prompt: { chars: 1266, tokens: 316 },
      continuation_task: { chars: 1200, tokens: 300 },
      telegram_agent_prompt: { chars: 1007, tokens: 251 },
      execute_task: { chars: 934, tokens: 233 },
      _total: { tokens: 2283 },
    },
  }
}

export function useContextStats(refreshInterval = 5000) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/context/stats`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const result = await response.json()
      setData(result)
      setError(null)
    } catch (err) {
      console.error('Context stats fetch error:', err)
      setError(err.message)
      // Use demo data on error
      setData(generateDemoStats())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, refreshInterval)
    return () => clearInterval(interval)
  }, [fetchData, refreshInterval])

  return { data, loading, error, refetch: fetchData }
}

export function usePromptStats() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/context/prompts`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const result = await response.json()
      setData(result)
      setError(null)
    } catch (err) {
      console.error('Prompt stats fetch error:', err)
      setError(err.message)
      // Use demo data
      setData({
        orchestrator_prompt: { chars: 1858, tokens: 464 },
        coding_agent_prompt: { chars: 1604, tokens: 401 },
        task_agent_prompt: { chars: 1272, tokens: 318 },
        reviewer_prompt: { chars: 1266, tokens: 316 },
        continuation_task: { chars: 1200, tokens: 300 },
        telegram_agent_prompt: { chars: 1007, tokens: 251 },
        execute_task: { chars: 934, tokens: 233 },
        _total: { tokens: 2283 },
        _savings: {
          before: 9896,
          after: 2283,
          percent: 76.9,
        },
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { data, loading, error, refetch: fetchData }
}

export default useContextStats
