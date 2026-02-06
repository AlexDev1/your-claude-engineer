import React, { useState, useCallback, useMemo } from 'react'
import { Plus, RefreshCw, LayoutGrid, List, Search, Filter } from 'lucide-react'
import KanbanBoard from '../components/KanbanBoard'
import IssueEditor from '../components/IssueEditor'
import CreateIssueForm from '../components/CreateIssueForm'
import BulkActions from '../components/BulkActions'
import useIssues from '../hooks/useIssues'
import { useKeyboardShortcuts, SHORTCUTS } from '../hooks/useKeyboardShortcuts'

function TaskManager() {
  const {
    issues,
    loading,
    error,
    refetch,
    createIssue,
    updateIssue,
    deleteIssue,
    addComment,
    bulkOperation,
    undo,
  } = useIssues()

  const [selectedIssues, setSelectedIssues] = useState([])
  const [editingIssue, setEditingIssue] = useState(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [viewMode, setViewMode] = useState('kanban') // 'kanban' | 'list'
  const [searchQuery, setSearchQuery] = useState('')
  const [priorityFilter, setPriorityFilter] = useState(null)
  const [canUndo, setCanUndo] = useState(false)

  // Filter issues based on search and priority
  const filteredIssues = useMemo(() => {
    return issues.filter(issue => {
      const matchesSearch = !searchQuery ||
        issue.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        issue.identifier.toLowerCase().includes(searchQuery.toLowerCase())

      const matchesPriority = !priorityFilter || issue.priority === priorityFilter

      return matchesSearch && matchesPriority
    })
  }, [issues, searchQuery, priorityFilter])

  // Handlers
  const handleStateChange = useCallback(async (issueId, newState) => {
    await updateIssue(issueId, { state: newState })
    setCanUndo(true)
  }, [updateIssue])

  const handlePriorityChange = useCallback(async (issueId, newPriority) => {
    await updateIssue(issueId, { priority: newPriority })
    setCanUndo(true)
  }, [updateIssue])

  const handleCommentAdd = useCallback(async (issueId, content) => {
    await addComment(issueId, content)
  }, [addComment])

  const handleEdit = useCallback((issue) => {
    setEditingIssue(issue)
  }, [])

  const handleSave = useCallback(async (issueId, data) => {
    if (issueId) {
      await updateIssue(issueId, data)
    } else {
      await createIssue(data)
    }
    setCanUndo(true)
  }, [updateIssue, createIssue])

  const handleDelete = useCallback(async (issueId) => {
    await deleteIssue(issueId)
    setCanUndo(true)
  }, [deleteIssue])

  const handleCreate = useCallback(async (data) => {
    await createIssue(data)
    setCanUndo(true)
  }, [createIssue])

  const handleSelectIssue = useCallback((issueId) => {
    setSelectedIssues(prev => {
      if (prev.includes(issueId)) {
        return prev.filter(id => id !== issueId)
      }
      return [...prev, issueId]
    })
  }, [])

  const handleSelectMultiple = useCallback((issueId, isRange) => {
    if (!isRange || selectedIssues.length === 0) {
      handleSelectIssue(issueId)
      return
    }

    // Find the range of issues between last selected and current
    const lastSelected = selectedIssues[selectedIssues.length - 1]
    const issueIds = filteredIssues.map(i => i.identifier)
    const lastIndex = issueIds.indexOf(lastSelected)
    const currentIndex = issueIds.indexOf(issueId)

    if (lastIndex === -1 || currentIndex === -1) return

    const start = Math.min(lastIndex, currentIndex)
    const end = Math.max(lastIndex, currentIndex)
    const range = issueIds.slice(start, end + 1)

    setSelectedIssues(prev => {
      const newSelection = new Set(prev)
      range.forEach(id => newSelection.add(id))
      return Array.from(newSelection)
    })
  }, [selectedIssues, filteredIssues, handleSelectIssue])

  const handleClearSelection = useCallback(() => {
    setSelectedIssues([])
  }, [])

  const handleBulkOperation = useCallback(async (operation, value) => {
    if (selectedIssues.length === 0) return

    await bulkOperation(selectedIssues, operation, value)
    setSelectedIssues([])
    setCanUndo(true)
  }, [selectedIssues, bulkOperation])

  const handleUndo = useCallback(async () => {
    const result = await undo()
    if (!result) {
      setCanUndo(false)
    }
  }, [undo])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    [SHORTCUTS.NEW_ISSUE]: () => setShowCreateForm(true),
    [SHORTCUTS.CANCEL]: () => {
      if (editingIssue) {
        setEditingIssue(null)
      } else if (showCreateForm) {
        setShowCreateForm(false)
      } else if (selectedIssues.length > 0) {
        setSelectedIssues([])
      }
    },
    [SHORTCUTS.UNDO]: () => {
      if (canUndo) handleUndo()
    },
    [SHORTCUTS.PRIORITY_URGENT]: () => {
      if (selectedIssues.length === 1) {
        handlePriorityChange(selectedIssues[0], 'urgent')
      }
    },
    [SHORTCUTS.PRIORITY_HIGH]: () => {
      if (selectedIssues.length === 1) {
        handlePriorityChange(selectedIssues[0], 'high')
      }
    },
    [SHORTCUTS.PRIORITY_MEDIUM]: () => {
      if (selectedIssues.length === 1) {
        handlePriorityChange(selectedIssues[0], 'medium')
      }
    },
    [SHORTCUTS.PRIORITY_LOW]: () => {
      if (selectedIssues.length === 1) {
        handlePriorityChange(selectedIssues[0], 'low')
      }
    },
    [SHORTCUTS.EDIT]: () => {
      if (selectedIssues.length === 1) {
        const issue = issues.find(i => i.identifier === selectedIssues[0])
        if (issue) handleEdit(issue)
      }
    },
    [SHORTCUTS.DELETE]: () => {
      if (selectedIssues.length > 0) {
        handleBulkOperation('delete', null)
      }
    },
  }, { enabled: !editingIssue && !showCreateForm })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Task Manager</h2>
          <p className="text-gray-400 mt-1">
            Manage and track your issues
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search issues..."
              className="w-48 bg-gray-800 text-white text-sm pl-9 pr-3 py-2 rounded-lg border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Priority Filter */}
          <select
            value={priorityFilter || ''}
            onChange={(e) => setPriorityFilter(e.target.value || null)}
            className="bg-gray-800 text-white text-sm px-3 py-2 rounded-lg border border-gray-700 focus:border-blue-500"
          >
            <option value="">All Priorities</option>
            <option value="urgent">Urgent</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          {/* View Toggle */}
          <div className="flex bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => setViewMode('kanban')}
              className={`p-2 rounded ${viewMode === 'kanban' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
              title="Kanban view"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 rounded ${viewMode === 'list' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
              title="List view"
            >
              <List className="w-4 h-4" />
            </button>
          </div>

          {/* Refresh */}
          <button
            onClick={refetch}
            disabled={loading}
            className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-5 h-5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {/* Create Issue */}
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>New Issue</span>
          </button>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-red-400">
          <p className="font-medium">Error loading issues</p>
          <p className="text-sm mt-1">{error}</p>
          <p className="text-sm mt-2 text-gray-400">Showing demo data instead.</p>
        </div>
      )}

      {/* Loading State */}
      {loading && issues.length === 0 && (
        <div className="flex items-center justify-center h-64">
          <div className="flex items-center space-x-3 text-gray-400">
            <RefreshCw className="w-6 h-6 animate-spin" />
            <span>Loading issues...</span>
          </div>
        </div>
      )}

      {/* Main Content */}
      {!loading || issues.length > 0 ? (
        viewMode === 'kanban' ? (
          <KanbanBoard
            issues={filteredIssues}
            onStateChange={handleStateChange}
            onPriorityChange={handlePriorityChange}
            onCommentAdd={handleCommentAdd}
            onEdit={handleEdit}
            selectedIssues={selectedIssues}
            onSelectIssue={handleSelectIssue}
            onSelectMultiple={handleSelectMultiple}
          />
        ) : (
          <ListView
            issues={filteredIssues}
            onStateChange={handleStateChange}
            onPriorityChange={handlePriorityChange}
            onEdit={handleEdit}
            selectedIssues={selectedIssues}
            onSelectIssue={handleSelectIssue}
          />
        )
      ) : null}

      {/* Keyboard Shortcuts Help */}
      <div className="bg-gray-800/50 rounded-xl p-4 border border-gray-700/50">
        <h4 className="text-sm font-medium text-white mb-2">Keyboard Shortcuts</h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-gray-400">
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">N</kbd> New issue</div>
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">E</kbd> Edit selected</div>
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">1-4</kbd> Set priority</div>
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">Ctrl+Z</kbd> Undo</div>
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">Esc</kbd> Cancel/Clear</div>
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">Del</kbd> Delete selected</div>
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">Shift+Click</kbd> Select range</div>
          <div><kbd className="bg-gray-700 px-1.5 py-0.5 rounded">Ctrl+Click</kbd> Multi-select</div>
        </div>
      </div>

      {/* Bulk Actions Bar */}
      <BulkActions
        selectedCount={selectedIssues.length}
        onClearSelection={handleClearSelection}
        onBulkOperation={handleBulkOperation}
        onUndo={handleUndo}
        canUndo={canUndo}
      />

      {/* Modals */}
      <IssueEditor
        issue={editingIssue}
        isOpen={!!editingIssue}
        onClose={() => setEditingIssue(null)}
        onSave={handleSave}
        onDelete={handleDelete}
        allIssues={issues}
      />

      <CreateIssueForm
        isOpen={showCreateForm}
        onClose={() => setShowCreateForm(false)}
        onCreate={handleCreate}
        allIssues={issues}
      />
    </div>
  )
}

// Simple List View component
function ListView({ issues, onStateChange, onPriorityChange, onEdit, selectedIssues, onSelectIssue }) {
  const PRIORITY_COLORS = {
    urgent: 'bg-red-500',
    high: 'bg-orange-500',
    medium: 'bg-yellow-500',
    low: 'bg-green-500',
  }

  const STATE_COLORS = {
    'Todo': 'bg-gray-500',
    'In Progress': 'bg-blue-500',
    'Done': 'bg-green-500',
    'Cancelled': 'bg-red-500',
  }

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="bg-gray-800/50 border-b border-gray-700">
            <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 w-8">
              <input type="checkbox" className="rounded bg-gray-700 border-gray-600" disabled />
            </th>
            <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">ID</th>
            <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Title</th>
            <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">State</th>
            <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Priority</th>
            <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Type</th>
            <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {issues.map(issue => {
            const isSelected = selectedIssues.includes(issue.identifier)
            return (
              <tr
                key={issue.identifier}
                onClick={() => onSelectIssue(issue.identifier)}
                className={`hover:bg-gray-700/50 cursor-pointer transition-colors ${
                  isSelected ? 'bg-blue-500/10' : ''
                }`}
              >
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onSelectIssue(issue.identifier)}
                    className="rounded bg-gray-700 border-gray-600 text-blue-500"
                  />
                </td>
                <td className="px-4 py-3 text-sm text-gray-400">{issue.identifier}</td>
                <td className="px-4 py-3">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onEdit(issue)
                    }}
                    className="text-sm text-white hover:text-blue-400 transition-colors text-left"
                  >
                    {issue.title}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center px-2 py-1 rounded text-xs text-white ${STATE_COLORS[issue.state] || 'bg-gray-500'}`}>
                    {issue.state}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-block w-3 h-3 rounded-full ${PRIORITY_COLORS[issue.priority] || 'bg-gray-500'}`} title={issue.priority} />
                </td>
                <td className="px-4 py-3 text-sm text-gray-400">{issue.issue_type}</td>
                <td className="px-4 py-3">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onEdit(issue)
                    }}
                    className="text-sm text-blue-400 hover:text-blue-300"
                  >
                    Edit
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {issues.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          No issues found
        </div>
      )}
    </div>
  )
}

export default TaskManager
