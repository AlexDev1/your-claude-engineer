import { useState, useEffect, useCallback } from 'react'

const API_BASE = '/api'

export function useIssues(team = 'ENG') {
  const [issues, setIssues] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchIssues = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/issues?team=${team}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch issues: ${response.status}`)
      }
      const result = await response.json()
      setIssues(result.issues || [])
    } catch (err) {
      console.error('Issues fetch error:', err)
      setError(err.message)
      // Использовать mock-данные при ошибке
      setIssues(generateMockIssues())
    } finally {
      setLoading(false)
    }
  }, [team])

  useEffect(() => {
    fetchIssues()
  }, [fetchIssues])

  const createIssue = async (issueData) => {
    try {
      const response = await fetch(`${API_BASE}/issues`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(issueData),
      })
      if (!response.ok) throw new Error('Failed to create issue')
      const newIssue = await response.json()
      setIssues(prev => [...prev, newIssue])
      return newIssue
    } catch (err) {
      console.error('Create issue error:', err)
      // Оптимистичное обновление для демо
      const mockIssue = {
        identifier: `ENG-${Date.now() % 1000}`,
        ...issueData,
        state: 'Todo',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        comments: [],
      }
      setIssues(prev => [...prev, mockIssue])
      return mockIssue
    }
  }

  const updateIssue = async (issueId, updates) => {
    try {
      const response = await fetch(`${API_BASE}/issues/${issueId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      if (!response.ok) throw new Error('Failed to update issue')
      const updatedIssue = await response.json()
      setIssues(prev => prev.map(i => i.identifier === issueId ? updatedIssue : i))
      return updatedIssue
    } catch (err) {
      console.error('Update issue error:', err)
      // Оптимистичное обновление для демо
      setIssues(prev => prev.map(i =>
        i.identifier === issueId
          ? { ...i, ...updates, updated_at: new Date().toISOString() }
          : i
      ))
      return { identifier: issueId, ...updates }
    }
  }

  const deleteIssue = async (issueId) => {
    try {
      const response = await fetch(`${API_BASE}/issues/${issueId}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('Failed to delete issue')
      setIssues(prev => prev.filter(i => i.identifier !== issueId))
      return true
    } catch (err) {
      console.error('Delete issue error:', err)
      // Оптимистичное обновление для демо
      setIssues(prev => prev.filter(i => i.identifier !== issueId))
      return true
    }
  }

  const addComment = async (issueId, content) => {
    try {
      const response = await fetch(`${API_BASE}/issues/${issueId}/comments?content=${encodeURIComponent(content)}`, {
        method: 'POST',
      })
      if (!response.ok) throw new Error('Failed to add comment')
      const comment = await response.json()
      setIssues(prev => prev.map(i =>
        i.identifier === issueId
          ? { ...i, comments: [...(i.comments || []), comment] }
          : i
      ))
      return comment
    } catch (err) {
      console.error('Add comment error:', err)
      // Оптимистичное обновление для демо
      const mockComment = {
        id: Date.now().toString(),
        author: 'Agent',
        content,
        created_at: new Date().toISOString(),
      }
      setIssues(prev => prev.map(i =>
        i.identifier === issueId
          ? { ...i, comments: [...(i.comments || []), mockComment] }
          : i
      ))
      return mockComment
    }
  }

  const bulkOperation = async (issueIds, operation, value) => {
    try {
      const response = await fetch(`${API_BASE}/issues/bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issue_ids: issueIds, operation, value }),
      })
      if (!response.ok) throw new Error('Failed to perform bulk operation')
      await fetchIssues() // Обновить после массовой операции
      return true
    } catch (err) {
      console.error('Bulk operation error:', err)
      // Оптимистичное обновление для демо
      if (operation === 'change_state') {
        setIssues(prev => prev.map(i =>
          issueIds.includes(i.identifier) ? { ...i, state: value } : i
        ))
      } else if (operation === 'change_priority') {
        setIssues(prev => prev.map(i =>
          issueIds.includes(i.identifier) ? { ...i, priority: value } : i
        ))
      } else if (operation === 'delete') {
        setIssues(prev => prev.filter(i => !issueIds.includes(i.identifier)))
      }
      return true
    }
  }

  const undo = async () => {
    try {
      const response = await fetch(`${API_BASE}/issues/undo`, { method: 'POST' })
      if (!response.ok) throw new Error('Failed to undo')
      await fetchIssues()
      return true
    } catch (err) {
      console.error('Undo error:', err)
      return false
    }
  }

  return {
    issues,
    loading,
    error,
    refetch: fetchIssues,
    createIssue,
    updateIssue,
    deleteIssue,
    addComment,
    bulkOperation,
    undo,
  }
}

function generateMockIssues() {
  const now = new Date()
  const issues = []
  const priorities = ['urgent', 'high', 'medium', 'low']
  const states = ['Done', 'Done', 'Done', 'In Progress', 'In Progress', 'Todo', 'Cancelled']
  const types = ['Feature', 'Bug', 'Task', 'Epic']

  for (let i = 1; i <= 20; i++) {
    const created = new Date(now - (i % 30) * 24 * 60 * 60 * 1000)
    const state = states[i % states.length]
    const completed = state === 'Done' ? new Date(created.getTime() + (i % 8 + 1) * 60 * 60 * 1000) : null

    issues.push({
      identifier: `ENG-${i}`,
      title: `${types[i % types.length]}: Task ${i} implementation`,
      description: `Detailed description for task ${i}. This includes requirements and acceptance criteria.`,
      state,
      priority: priorities[i % priorities.length],
      issue_type: types[i % types.length],
      team: 'ENG',
      project: 'Agent Dashboard',
      parent_id: null,
      dependencies: [],
      comments: [],
      created_at: created.toISOString(),
      updated_at: (completed || now).toISOString(),
      completed_at: completed ? completed.toISOString() : null,
    })
  }

  return issues
}

export default useIssues
