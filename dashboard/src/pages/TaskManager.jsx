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

  // Фильтровать задачи на основе поиска и приоритета
  const filteredIssues = useMemo(() => {
    return issues.filter(issue => {
      const matchesSearch = !searchQuery ||
        issue.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        issue.identifier.toLowerCase().includes(searchQuery.toLowerCase())

      const matchesPriority = !priorityFilter || issue.priority === priorityFilter

      return matchesSearch && matchesPriority
    })
  }, [issues, searchQuery, priorityFilter])

  // Обработчики событий
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

  // Очистить выделение
  const handleClearSelection = useCallback(() => {
    setSelectedIssues([])
  }, [])

  // Массовая операция
  const handleBulkOperation = useCallback(async (operation, value) => {
    if (selectedIssues.length === 0) return

    await bulkOperation(selectedIssues, operation, value)
    setSelectedIssues([])
    setCanUndo(true)
  }, [selectedIssues, bulkOperation])

  // Отменить последнее действие
  const handleUndo = useCallback(async () => {
    const result = await undo()
    if (!result) {
      setCanUndo(false)
    }
  }, [undo])

  // Горячие клавиши
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
          <h2
            className="text-2xl font-bold"
            style={{ color: 'var(--color-text)' }}
          >
            Менеджер задач
          </h2>
          <p
            className="mt-1"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            Управление и отслеживание задач
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {/* Search */}
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
              style={{ color: 'var(--color-textMuted)' }}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск задач..."
              className="w-48 text-sm pl-9 pr-3 py-2 rounded-lg border focus:ring-1"
              style={{
                backgroundColor: 'var(--color-inputBg)',
                borderColor: 'var(--color-inputBorder)',
                color: 'var(--color-text)'
              }}
            />
          </div>

          {/* Priority Filter */}
          <select
            value={priorityFilter || ''}
            onChange={(e) => setPriorityFilter(e.target.value || null)}
            className="text-sm px-3 py-2 rounded-lg border"
            style={{
              backgroundColor: 'var(--color-inputBg)',
              borderColor: 'var(--color-inputBorder)',
              color: 'var(--color-text)'
            }}
          >
            <option value="">Все приоритеты</option>
            <option value="urgent">Срочный</option>
            <option value="high">Высокий</option>
            <option value="medium">Средний</option>
            <option value="low">Низкий</option>
          </select>

          {/* View Toggle */}
          <div
            className="flex rounded-lg p-1"
            style={{ backgroundColor: 'var(--color-cardBg)' }}
          >
            <button
              onClick={() => setViewMode('kanban')}
              className="p-2 rounded transition-colors"
              style={{
                backgroundColor: viewMode === 'kanban' ? 'var(--color-bgTertiary)' : 'transparent',
                color: viewMode === 'kanban' ? 'var(--color-text)' : 'var(--color-textMuted)'
              }}
              title="Канбан"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className="p-2 rounded transition-colors"
              style={{
                backgroundColor: viewMode === 'list' ? 'var(--color-bgTertiary)' : 'transparent',
                color: viewMode === 'list' ? 'var(--color-text)' : 'var(--color-textMuted)'
              }}
              title="Список"
            >
              <List className="w-4 h-4" />
            </button>
          </div>

          {/* Refresh */}
          <button
            onClick={refetch}
            disabled={loading}
            className="p-2 rounded-lg transition-colors disabled:opacity-50"
            style={{
              backgroundColor: 'var(--color-cardBg)',
              color: 'var(--color-textSecondary)'
            }}
            title="Обновить"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {/* Create Issue */}
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors"
            style={{
              backgroundColor: 'var(--color-accent)',
              color: 'white'
            }}
          >
            <Plus className="w-4 h-4" />
            <span>Новая задача</span>
          </button>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div
          className="rounded-lg p-4 border"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171'
          }}
        >
          <p className="font-medium">Ошибка загрузки задач</p>
          <p className="text-sm mt-1">{error}</p>
          <p className="text-sm mt-2" style={{ color: 'var(--color-textSecondary)' }}>
            Показаны демо-данные.
          </p>
        </div>
      )}

      {/* Loading State */}
      {loading && issues.length === 0 && (
        <div className="flex items-center justify-center h-64">
          <div
            className="flex items-center space-x-3"
            style={{ color: 'var(--color-textSecondary)' }}
          >
            <RefreshCw className="w-6 h-6 animate-spin" />
            <span>Загрузка задач...</span>
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
      <div
        className="rounded-xl p-4 border"
        style={{
          backgroundColor: 'var(--color-cardBg)',
          borderColor: 'var(--color-cardBorder)'
        }}
      >
        <h4
          className="text-sm font-medium mb-2"
          style={{ color: 'var(--color-text)' }}
        >
          Горячие клавиши
        </h4>
        <div
          className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >N</kbd> Новая задача
          </div>
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >E</kbd> Редактировать
          </div>
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >1-4</kbd> Приоритет
          </div>
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >Ctrl+Z</kbd> Отмена
          </div>
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >Esc</kbd> Отменить/Очистить
          </div>
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >Del</kbd> Удалить выбранное
          </div>
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >Shift+Click</kbd> Выбрать диапазон
          </div>
          <div>
            <kbd
              className="px-1.5 py-0.5 rounded"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >Ctrl+Click</kbd> Множественный выбор
          </div>
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

// Простой компонент списка
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
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)'
      }}
    >
      <table className="w-full">
        <thead>
          <tr
            className="border-b"
            style={{
              backgroundColor: 'var(--color-bgSecondary)',
              borderColor: 'var(--color-border)'
            }}
          >
            <th
              className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3 w-8"
              style={{ color: 'var(--color-textMuted)' }}
            >
              <input type="checkbox" className="rounded" disabled style={{ backgroundColor: 'var(--color-inputBg)' }} />
            </th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: 'var(--color-textMuted)' }}>ID</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: 'var(--color-textMuted)' }}>Название</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: 'var(--color-textMuted)' }}>Статус</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: 'var(--color-textMuted)' }}>Приоритет</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: 'var(--color-textMuted)' }}>Тип</th>
            <th className="text-left text-xs font-medium uppercase tracking-wider px-4 py-3" style={{ color: 'var(--color-textMuted)' }}>Действия</th>
          </tr>
        </thead>
        <tbody className="divide-y" style={{ borderColor: 'var(--color-border)' }}>
          {issues.map(issue => {
            const isSelected = selectedIssues.includes(issue.identifier)
            return (
              <tr
                key={issue.identifier}
                onClick={() => onSelectIssue(issue.identifier)}
                className="cursor-pointer transition-colors"
                style={{
                  backgroundColor: isSelected ? 'rgba(96, 165, 250, 0.1)' : 'transparent'
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) e.currentTarget.style.backgroundColor = 'var(--color-bgSecondary)'
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent'
                }}
              >
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onSelectIssue(issue.identifier)}
                    className="rounded"
                    style={{
                      backgroundColor: 'var(--color-inputBg)',
                      borderColor: 'var(--color-inputBorder)'
                    }}
                  />
                </td>
                <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-textSecondary)' }}>{issue.identifier}</td>
                <td className="px-4 py-3">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onEdit(issue)
                    }}
                    className="text-sm text-left transition-colors"
                    style={{ color: 'var(--color-text)' }}
                    onMouseEnter={(e) => e.currentTarget.style.color = 'var(--color-accent)'}
                    onMouseLeave={(e) => e.currentTarget.style.color = 'var(--color-text)'}
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
                <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-textSecondary)' }}>{issue.issue_type}</td>
                <td className="px-4 py-3">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onEdit(issue)
                    }}
                    className="text-sm transition-colors"
                    style={{ color: 'var(--color-accent)' }}
                  >
                    Изменить
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {issues.length === 0 && (
        <div
          className="text-center py-12"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          Задачи не найдены
        </div>
      )}
    </div>
  )
}

export default TaskManager
