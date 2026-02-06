import React, { useState, useRef } from 'react'
import { GripVertical, Flag, MessageSquare, Link2, Clock, CheckCircle2 } from 'lucide-react'
import QuickActions from './QuickActions'

const COLUMNS = [
  { id: 'Todo', label: 'Todo', color: 'border-gray-500', bg: 'bg-gray-500' },
  { id: 'In Progress', label: 'In Progress', color: 'border-blue-500', bg: 'bg-blue-500' },
  { id: 'Done', label: 'Done', color: 'border-green-500', bg: 'bg-green-500' },
  { id: 'Cancelled', label: 'Cancelled', color: 'border-red-500', bg: 'bg-red-500' },
]

const PRIORITY_COLORS = {
  urgent: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
}

function KanbanBoard({
  issues,
  onStateChange,
  onPriorityChange,
  onCommentAdd,
  onEdit,
  selectedIssues,
  onSelectIssue,
  onSelectMultiple,
}) {
  const [draggedIssue, setDraggedIssue] = useState(null)
  const [dragOverColumn, setDragOverColumn] = useState(null)
  const dragCounter = useRef(0)

  const getIssuesByState = (state) => {
    return issues.filter(issue => issue.state === state)
  }

  const handleDragStart = (e, issue) => {
    setDraggedIssue(issue)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', issue.identifier)
    // Add drag ghost styling
    e.target.style.opacity = '0.5'
  }

  const handleDragEnd = (e) => {
    e.target.style.opacity = '1'
    setDraggedIssue(null)
    setDragOverColumn(null)
    dragCounter.current = 0
  }

  const handleDragEnter = (e, columnId) => {
    e.preventDefault()
    dragCounter.current++
    setDragOverColumn(columnId)
  }

  const handleDragLeave = (e) => {
    dragCounter.current--
    if (dragCounter.current === 0) {
      setDragOverColumn(null)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDrop = (e, columnId) => {
    e.preventDefault()
    dragCounter.current = 0
    setDragOverColumn(null)

    if (draggedIssue && draggedIssue.state !== columnId) {
      // Check if transition is valid
      const validTransitions = {
        'Todo': ['In Progress', 'Cancelled'],
        'In Progress': ['Todo', 'Done', 'Cancelled'],
        'Done': ['In Progress'],
        'Cancelled': ['Todo'],
      }

      if (validTransitions[draggedIssue.state]?.includes(columnId)) {
        onStateChange(draggedIssue.identifier, columnId)
      }
    }
    setDraggedIssue(null)
  }

  const handleCardClick = (e, issue) => {
    if (e.shiftKey && selectedIssues.length > 0) {
      // Shift+Click: select range
      onSelectMultiple(issue.identifier, true)
    } else if (e.ctrlKey || e.metaKey) {
      // Ctrl/Cmd+Click: toggle selection
      onSelectIssue(issue.identifier)
    }
    // Regular click is handled by QuickActions or double-click
  }

  const handleCardDoubleClick = (issue) => {
    onEdit(issue)
  }

  const isValidDropTarget = (columnId) => {
    if (!draggedIssue) return false
    if (draggedIssue.state === columnId) return false

    const validTransitions = {
      'Todo': ['In Progress', 'Cancelled'],
      'In Progress': ['Todo', 'Done', 'Cancelled'],
      'Done': ['In Progress'],
      'Cancelled': ['Todo'],
    }

    return validTransitions[draggedIssue.state]?.includes(columnId)
  }

  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {COLUMNS.map(column => {
        const columnIssues = getIssuesByState(column.id)
        const isDropTarget = isValidDropTarget(column.id)
        const isDragOver = dragOverColumn === column.id

        return (
          <div
            key={column.id}
            className={`flex-1 min-w-[280px] max-w-[350px] bg-gray-800/50 rounded-xl border transition-all ${
              isDragOver && isDropTarget
                ? `${column.color} border-2 bg-gray-700/50`
                : 'border-gray-700'
            }`}
            onDragEnter={(e) => handleDragEnter(e, column.id)}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, column.id)}
          >
            {/* Column Header */}
            <div className="flex items-center justify-between p-3 border-b border-gray-700">
              <div className="flex items-center space-x-2">
                <span className={`w-3 h-3 rounded-full ${column.bg}`} />
                <span className="font-medium text-white">{column.label}</span>
                <span className="text-xs text-gray-400 bg-gray-700 px-2 py-0.5 rounded-full">
                  {columnIssues.length}
                </span>
              </div>
            </div>

            {/* Cards */}
            <div className="p-2 space-y-2 min-h-[200px] max-h-[600px] overflow-y-auto">
              {columnIssues.map(issue => {
                const isSelected = selectedIssues.includes(issue.identifier)
                const priorityColor = PRIORITY_COLORS[issue.priority] || PRIORITY_COLORS.medium

                return (
                  <div
                    key={issue.identifier}
                    draggable
                    onDragStart={(e) => handleDragStart(e, issue)}
                    onDragEnd={handleDragEnd}
                    onClick={(e) => handleCardClick(e, issue)}
                    onDoubleClick={() => handleCardDoubleClick(issue)}
                    className={`group bg-gray-700 hover:bg-gray-600 rounded-lg p-3 cursor-grab active:cursor-grabbing transition-all border ${
                      isSelected
                        ? 'border-blue-500 ring-1 ring-blue-500'
                        : 'border-transparent hover:border-gray-500'
                    } ${draggedIssue?.identifier === issue.identifier ? 'opacity-50' : ''}`}
                  >
                    {/* Card Header */}
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        <GripVertical className="w-4 h-4 text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                        <span className="text-xs text-gray-400">{issue.identifier}</span>
                        <span className={`w-2 h-2 rounded-full ${priorityColor}`} title={issue.priority} />
                      </div>
                      <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                        <QuickActions
                          issue={issue}
                          onPriorityChange={onPriorityChange}
                          onStateChange={onStateChange}
                          onCommentAdd={onCommentAdd}
                          onEdit={onEdit}
                        />
                      </div>
                    </div>

                    {/* Card Title */}
                    <h4 className="text-sm text-white font-medium mb-2 line-clamp-2">
                      {issue.title}
                    </h4>

                    {/* Card Meta */}
                    <div className="flex items-center justify-between text-xs text-gray-400">
                      <div className="flex items-center space-x-2">
                        {issue.issue_type && (
                          <span className="bg-gray-600 px-1.5 py-0.5 rounded">
                            {issue.issue_type}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center space-x-2">
                        {issue.dependencies?.length > 0 && (
                          <span className="flex items-center" title={`${issue.dependencies.length} dependencies`}>
                            <Link2 className="w-3 h-3" />
                          </span>
                        )}
                        {issue.comments?.length > 0 && (
                          <span className="flex items-center" title={`${issue.comments.length} comments`}>
                            <MessageSquare className="w-3 h-3 mr-0.5" />
                            {issue.comments.length}
                          </span>
                        )}
                        {issue.state === 'Done' && issue.completed_at && (
                          <span className="flex items-center text-green-400" title="Completed">
                            <CheckCircle2 className="w-3 h-3" />
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* Empty State */}
              {columnIssues.length === 0 && (
                <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
                  {draggedIssue && isDropTarget ? (
                    <span>Drop here to move</span>
                  ) : (
                    <span>No issues</span>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default KanbanBoard
