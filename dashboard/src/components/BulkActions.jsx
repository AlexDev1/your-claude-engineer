import React, { useState } from 'react'
import { X, Trash2, Flag, ArrowRight, Folder, Undo2 } from 'lucide-react'

const PRIORITY_OPTIONS = [
  { value: 'urgent', label: 'Urgent', color: 'bg-red-500' },
  { value: 'high', label: 'High', color: 'bg-orange-500' },
  { value: 'medium', label: 'Medium', color: 'bg-yellow-500' },
  { value: 'low', label: 'Low', color: 'bg-green-500' },
]

const STATE_OPTIONS = [
  { value: 'Todo', label: 'Todo', color: 'bg-gray-500' },
  { value: 'In Progress', label: 'In Progress', color: 'bg-blue-500' },
  { value: 'Done', label: 'Done', color: 'bg-green-500' },
  { value: 'Cancelled', label: 'Cancelled', color: 'bg-red-500' },
]

const PROJECT_OPTIONS = ['Agent Dashboard', 'Core Platform', 'Infrastructure', 'Documentation']

function BulkActions({ selectedCount, onClearSelection, onBulkOperation, onUndo, canUndo }) {
  const [showStates, setShowStates] = useState(false)
  const [showPriorities, setShowPriorities] = useState(false)
  const [showProjects, setShowProjects] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  if (selectedCount === 0) return null

  const handleStateChange = (state) => {
    onBulkOperation('change_state', state)
    setShowStates(false)
  }

  const handlePriorityChange = (priority) => {
    onBulkOperation('change_priority', priority)
    setShowPriorities(false)
  }

  const handleProjectChange = (project) => {
    onBulkOperation('assign_project', project)
    setShowProjects(false)
  }

  const handleDelete = () => {
    if (showDeleteConfirm) {
      onBulkOperation('delete', null)
      setShowDeleteConfirm(false)
    } else {
      setShowDeleteConfirm(true)
    }
  }

  const closeAllDropdowns = () => {
    setShowStates(false)
    setShowPriorities(false)
    setShowProjects(false)
    setShowDeleteConfirm(false)
  }

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40">
      <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl p-3 flex items-center space-x-3">
        {/* Selected Count */}
        <div className="flex items-center space-x-2 pr-3 border-r border-gray-700">
          <span className="bg-blue-600 text-white text-sm font-medium px-2 py-0.5 rounded">
            {selectedCount}
          </span>
          <span className="text-gray-300 text-sm">selected</span>
          <button
            onClick={onClearSelection}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
            title="Clear selection"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* Change State */}
        <div className="relative">
          <button
            onClick={() => {
              closeAllDropdowns()
              setShowStates(!showStates)
            }}
            className="flex items-center space-x-1 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <ArrowRight className="w-4 h-4" />
            <span>State</span>
          </button>
          {showStates && (
            <div className="absolute bottom-full mb-2 left-0 bg-gray-700 border border-gray-600 rounded-lg shadow-lg py-1 min-w-[140px]">
              {STATE_OPTIONS.map(option => (
                <button
                  key={option.value}
                  onClick={() => handleStateChange(option.value)}
                  className="w-full flex items-center space-x-2 px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-600 transition-colors"
                >
                  <span className={`w-2 h-2 rounded-full ${option.color}`} />
                  <span>{option.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Change Priority */}
        <div className="relative">
          <button
            onClick={() => {
              closeAllDropdowns()
              setShowPriorities(!showPriorities)
            }}
            className="flex items-center space-x-1 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <Flag className="w-4 h-4" />
            <span>Priority</span>
          </button>
          {showPriorities && (
            <div className="absolute bottom-full mb-2 left-0 bg-gray-700 border border-gray-600 rounded-lg shadow-lg py-1 min-w-[120px]">
              {PRIORITY_OPTIONS.map(option => (
                <button
                  key={option.value}
                  onClick={() => handlePriorityChange(option.value)}
                  className="w-full flex items-center space-x-2 px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-600 transition-colors"
                >
                  <span className={`w-2 h-2 rounded-full ${option.color}`} />
                  <span>{option.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Assign Project */}
        <div className="relative">
          <button
            onClick={() => {
              closeAllDropdowns()
              setShowProjects(!showProjects)
            }}
            className="flex items-center space-x-1 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <Folder className="w-4 h-4" />
            <span>Project</span>
          </button>
          {showProjects && (
            <div className="absolute bottom-full mb-2 left-0 bg-gray-700 border border-gray-600 rounded-lg shadow-lg py-1 min-w-[160px]">
              {PROJECT_OPTIONS.map(project => (
                <button
                  key={project}
                  onClick={() => handleProjectChange(project)}
                  className="w-full text-left px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-600 transition-colors"
                >
                  {project}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="w-px h-6 bg-gray-700" />

        {/* Undo */}
        {canUndo && (
          <button
            onClick={onUndo}
            className="flex items-center space-x-1 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700 rounded-lg transition-colors"
            title="Undo last operation (Ctrl+Z)"
          >
            <Undo2 className="w-4 h-4" />
            <span>Undo</span>
          </button>
        )}

        {/* Delete */}
        <button
          onClick={handleDelete}
          className={`flex items-center space-x-1 px-3 py-1.5 text-sm rounded-lg transition-colors ${
            showDeleteConfirm
              ? 'bg-red-600 text-white'
              : 'text-red-400 hover:bg-red-500/20'
          }`}
        >
          <Trash2 className="w-4 h-4" />
          <span>{showDeleteConfirm ? 'Confirm' : 'Delete'}</span>
        </button>
      </div>

      {/* Keyboard Shortcuts Hint */}
      <div className="mt-2 text-center text-xs text-gray-500">
        Shift+Click to select range | Ctrl+Click to toggle | Escape to clear
      </div>
    </div>
  )
}

export default BulkActions
