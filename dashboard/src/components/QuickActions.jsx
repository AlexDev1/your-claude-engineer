import React, { useState } from 'react'
import { Flag, MessageSquare, ArrowRight, Edit2, MoreHorizontal } from 'lucide-react'

const PRIORITY_CONFIG = {
  urgent: { color: 'text-red-500', bg: 'bg-red-500/20', label: 'Срочный' },
  high: { color: 'text-orange-500', bg: 'bg-orange-500/20', label: 'Высокий' },
  medium: { color: 'text-yellow-500', bg: 'bg-yellow-500/20', label: 'Средний' },
  low: { color: 'text-green-500', bg: 'bg-green-500/20', label: 'Низкий' },
}

const STATE_TRANSITIONS = {
  'Todo': [
    { value: 'In Progress', label: 'Начать', color: 'bg-blue-600' },
    { value: 'Cancelled', label: 'Отменить', color: 'bg-gray-600' },
  ],
  'In Progress': [
    { value: 'Done', label: 'Завершить', color: 'bg-green-600' },
    { value: 'Todo', label: 'Вернуть в очередь', color: 'bg-gray-600' },
  ],
  'Done': [
    { value: 'In Progress', label: 'Возобновить', color: 'bg-blue-600' },
  ],
  'Cancelled': [
    { value: 'Todo', label: 'Восстановить', color: 'bg-gray-600' },
  ],
}

function QuickActions({ issue, onPriorityChange, onStateChange, onCommentAdd, onEdit }) {
  const [showPriorities, setShowPriorities] = useState(false)
  const [showTransitions, setShowTransitions] = useState(false)
  const [showComment, setShowComment] = useState(false)
  const [commentText, setCommentText] = useState('')

  const currentPriority = PRIORITY_CONFIG[issue.priority] || PRIORITY_CONFIG.medium
  const availableTransitions = STATE_TRANSITIONS[issue.state] || []

  const handlePrioritySelect = (priority) => {
    onPriorityChange(issue.identifier, priority)
    setShowPriorities(false)
  }

  const handleTransitionSelect = (state) => {
    onStateChange(issue.identifier, state)
    setShowTransitions(false)
  }

  const handleCommentSubmit = () => {
    if (commentText.trim()) {
      onCommentAdd(issue.identifier, commentText)
      setCommentText('')
      setShowComment(false)
    }
  }

  return (
    <div className="flex items-center space-x-1">
      {/* Priority Flag */}
      <div className="relative">
        <button
          onClick={() => {
            setShowPriorities(!showPriorities)
            setShowTransitions(false)
            setShowComment(false)
          }}
          className={`p-1.5 rounded hover:bg-gray-600 transition-colors ${currentPriority.color}`}
          title={`Приоритет: ${currentPriority.label}`}
        >
          <Flag className="w-4 h-4" />
        </button>

        {showPriorities && (
          <div className="absolute top-full right-0 mt-1 bg-gray-700 border border-gray-600 rounded-lg shadow-lg z-10 py-1 min-w-[120px]">
            {Object.entries(PRIORITY_CONFIG).map(([key, config]) => (
              <button
                key={key}
                onClick={() => handlePrioritySelect(key)}
                className={`w-full flex items-center space-x-2 px-3 py-1.5 text-sm hover:bg-gray-600 transition-colors ${
                  issue.priority === key ? 'bg-gray-600' : ''
                }`}
              >
                <Flag className={`w-3 h-3 ${config.color}`} />
                <span className="text-gray-200">{config.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* State Transition */}
      {availableTransitions.length > 0 && (
        <div className="relative">
          <button
            onClick={() => {
              setShowTransitions(!showTransitions)
              setShowPriorities(false)
              setShowComment(false)
            }}
            className="p-1.5 rounded hover:bg-gray-600 transition-colors text-gray-400"
            title="Изменить статус"
          >
            <ArrowRight className="w-4 h-4" />
          </button>

          {showTransitions && (
            <div className="absolute top-full right-0 mt-1 bg-gray-700 border border-gray-600 rounded-lg shadow-lg z-10 py-1 min-w-[140px]">
              {availableTransitions.map(transition => (
                <button
                  key={transition.value}
                  onClick={() => handleTransitionSelect(transition.value)}
                  className="w-full flex items-center space-x-2 px-3 py-1.5 text-sm hover:bg-gray-600 transition-colors"
                >
                  <span className={`w-2 h-2 rounded-full ${transition.color}`} />
                  <span className="text-gray-200">{transition.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Quick Comment */}
      <div className="relative">
        <button
          onClick={() => {
            setShowComment(!showComment)
            setShowPriorities(false)
            setShowTransitions(false)
          }}
          className="p-1.5 rounded hover:bg-gray-600 transition-colors text-gray-400"
          title="Добавить комментарий (C)"
        >
          <MessageSquare className="w-4 h-4" />
        </button>

        {showComment && (
          <div className="absolute top-full right-0 mt-1 bg-gray-700 border border-gray-600 rounded-lg shadow-lg z-10 p-2 min-w-[250px]">
            <textarea
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Быстрый комментарий..."
              className="w-full bg-gray-800 text-white text-sm rounded px-2 py-1.5 border border-gray-600 focus:border-blue-500 resize-none"
              rows={2}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleCommentSubmit()
                }
                if (e.key === 'Escape') {
                  setShowComment(false)
                }
              }}
            />
            <div className="flex justify-end mt-1">
              <button
                onClick={handleCommentSubmit}
                disabled={!commentText.trim()}
                className="px-2 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded disabled:opacity-50"
              >
                Добавить
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Edit Button */}
      <button
        onClick={() => onEdit(issue)}
        className="p-1.5 rounded hover:bg-gray-600 transition-colors text-gray-400"
        title="Редактировать (E)"
      >
        <Edit2 className="w-4 h-4" />
      </button>
    </div>
  )
}

export default QuickActions
