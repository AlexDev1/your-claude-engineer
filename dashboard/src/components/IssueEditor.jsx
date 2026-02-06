import React, { useState, useEffect, useRef } from 'react'
import { X, Save, Trash2, MessageSquare, Link2, Flag, ChevronDown } from 'lucide-react'

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

const VALID_TRANSITIONS = {
  'Todo': ['In Progress', 'Cancelled'],
  'In Progress': ['Todo', 'Done', 'Cancelled'],
  'Done': ['In Progress'],
  'Cancelled': ['Todo'],
}

function IssueEditor({ issue, isOpen, onClose, onSave, onDelete, allIssues = [] }) {
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    priority: 'medium',
    state: 'Todo',
    parent_id: null,
    dependencies: [],
  })
  const [newComment, setNewComment] = useState('')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [isPreviewMode, setIsPreviewMode] = useState(false)
  const titleRef = useRef(null)

  useEffect(() => {
    if (issue) {
      setFormData({
        title: issue.title || '',
        description: issue.description || '',
        priority: issue.priority || 'medium',
        state: issue.state || 'Todo',
        parent_id: issue.parent_id || null,
        dependencies: issue.dependencies || [],
      })
    }
  }, [issue])

  useEffect(() => {
    if (isOpen && titleRef.current) {
      titleRef.current.focus()
    }
  }, [isOpen])

  if (!isOpen) return null

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSave = () => {
    if (!formData.title.trim()) return
    onSave(issue?.identifier, formData)
    onClose()
  }

  const handleDelete = () => {
    if (showDeleteConfirm) {
      onDelete(issue.identifier)
      onClose()
    } else {
      setShowDeleteConfirm(true)
    }
  }

  const handleAddComment = () => {
    if (newComment.trim() && issue?.identifier) {
      // This would call the addComment function passed as prop
      // For now, we'll include it in the save
      setNewComment('')
    }
  }

  const getValidStates = () => {
    if (!issue) return STATE_OPTIONS.map(s => s.value)
    const current = issue.state || 'Todo'
    return [current, ...(VALID_TRANSITIONS[current] || [])]
  }

  const validStates = getValidStates()

  // Get potential parent issues (exclude self and children)
  const potentialParents = allIssues.filter(i =>
    i.identifier !== issue?.identifier && i.parent_id !== issue?.identifier
  )

  // Simple markdown preview
  const renderMarkdown = (text) => {
    if (!text) return ''
    return text
      .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold text-white mt-4 mb-2">$1</h3>')
      .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold text-white mt-4 mb-2">$1</h2>')
      .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold text-white mt-4 mb-2">$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code class="bg-gray-700 px-1 rounded">$1</code>')
      .replace(/\n/g, '<br/>')
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center space-x-3">
            <span className="text-sm text-gray-400">{issue?.identifier || 'New Issue'}</span>
            {issue?.issue_type && (
              <span className="px-2 py-0.5 bg-gray-700 text-gray-300 text-xs rounded">
                {issue.issue_type}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Title */}
          <input
            ref={titleRef}
            type="text"
            value={formData.title}
            onChange={(e) => handleChange('title', e.target.value)}
            placeholder="Issue title"
            className="w-full bg-transparent text-xl font-semibold text-white placeholder-gray-500 border-none outline-none focus:ring-0"
          />

          {/* State & Priority Row */}
          <div className="flex items-center space-x-4">
            {/* State Dropdown */}
            <div className="flex-1">
              <label className="block text-xs text-gray-400 mb-1">State</label>
              <select
                value={formData.state}
                onChange={(e) => handleChange('state', e.target.value)}
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              >
                {STATE_OPTIONS.map(option => (
                  <option
                    key={option.value}
                    value={option.value}
                    disabled={!validStates.includes(option.value)}
                  >
                    {option.label} {!validStates.includes(option.value) ? '(invalid transition)' : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Priority Dropdown */}
            <div className="flex-1">
              <label className="block text-xs text-gray-400 mb-1">Priority</label>
              <select
                value={formData.priority}
                onChange={(e) => handleChange('priority', e.target.value)}
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              >
                {PRIORITY_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Description */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs text-gray-400">Description (Markdown)</label>
              <button
                onClick={() => setIsPreviewMode(!isPreviewMode)}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                {isPreviewMode ? 'Edit' : 'Preview'}
              </button>
            </div>
            {isPreviewMode ? (
              <div
                className="w-full bg-gray-700/50 rounded-lg p-3 min-h-[120px] text-gray-200 prose prose-invert prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(formData.description) || '<span class="text-gray-500">No description</span>' }}
              />
            ) : (
              <textarea
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="Add a description... (Markdown supported)"
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 min-h-[120px] resize-y"
              />
            )}
          </div>

          {/* Parent Issue */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Parent Issue</label>
            <select
              value={formData.parent_id || ''}
              onChange={(e) => handleChange('parent_id', e.target.value || null)}
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            >
              <option value="">None</option>
              {potentialParents.map(i => (
                <option key={i.identifier} value={i.identifier}>
                  {i.identifier}: {i.title}
                </option>
              ))}
            </select>
          </div>

          {/* Dependencies */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Dependencies</label>
            <div className="flex flex-wrap gap-2 mb-2">
              {formData.dependencies.map(dep => (
                <span
                  key={dep}
                  className="inline-flex items-center bg-gray-700 text-gray-300 text-xs px-2 py-1 rounded"
                >
                  <Link2 className="w-3 h-3 mr-1" />
                  {dep}
                  <button
                    onClick={() => handleChange('dependencies', formData.dependencies.filter(d => d !== dep))}
                    className="ml-1 hover:text-red-400"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
            <select
              value=""
              onChange={(e) => {
                if (e.target.value && !formData.dependencies.includes(e.target.value)) {
                  handleChange('dependencies', [...formData.dependencies, e.target.value])
                }
              }}
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Add dependency...</option>
              {potentialParents
                .filter(i => !formData.dependencies.includes(i.identifier))
                .map(i => (
                  <option key={i.identifier} value={i.identifier}>
                    {i.identifier}: {i.title}
                  </option>
                ))}
            </select>
          </div>

          {/* Comments Section */}
          {issue && (
            <div>
              <label className="block text-xs text-gray-400 mb-2">
                <MessageSquare className="w-3 h-3 inline mr-1" />
                Comments ({issue.comments?.length || 0})
              </label>
              <div className="space-y-2 mb-2 max-h-32 overflow-y-auto">
                {(issue.comments || []).map(comment => (
                  <div key={comment.id} className="bg-gray-700/50 rounded p-2 text-sm">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-400 text-xs">{comment.author}</span>
                      <span className="text-gray-500 text-xs">
                        {new Date(comment.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-gray-200">{comment.content}</p>
                  </div>
                ))}
              </div>
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  placeholder="Add a comment..."
                  className="flex-1 bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500"
                  onKeyDown={(e) => e.key === 'Enter' && handleAddComment()}
                />
                <button
                  onClick={handleAddComment}
                  disabled={!newComment.trim()}
                  className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm disabled:opacity-50"
                >
                  Add
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-700 bg-gray-800/80">
          <div>
            {issue && (
              <button
                onClick={handleDelete}
                className={`flex items-center space-x-1 px-3 py-2 rounded-lg text-sm transition-colors ${
                  showDeleteConfirm
                    ? 'bg-red-600 text-white'
                    : 'text-red-400 hover:bg-red-500/20'
                }`}
              >
                <Trash2 className="w-4 h-4" />
                <span>{showDeleteConfirm ? 'Confirm Delete' : 'Delete'}</span>
              </button>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!formData.title.trim()}
              className="flex items-center space-x-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className="w-4 h-4" />
              <span>Save</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default IssueEditor
