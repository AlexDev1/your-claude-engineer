import React, { useState, useEffect, useRef } from 'react'
import { X, Save, Trash2, MessageSquare, Link2, Flag, ChevronDown } from 'lucide-react'

const PRIORITY_OPTIONS = [
  { value: 'urgent', label: 'Срочный', color: '#ef4444' },
  { value: 'high', label: 'Высокий', color: '#f97316' },
  { value: 'medium', label: 'Средний', color: '#eab308' },
  { value: 'low', label: 'Низкий', color: '#22c55e' },
]

const STATE_OPTIONS = [
  { value: 'Todo', label: 'К выполнению', color: '#6b7280' },
  { value: 'In Progress', label: 'В работе', color: '#3b82f6' },
  { value: 'Done', label: 'Готово', color: '#22c55e' },
  { value: 'Cancelled', label: 'Отменено', color: '#ef4444' },
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

  // Получить потенциальные родительские задачи (исключить себя и дочерние)
  const potentialParents = allIssues.filter(i =>
    i.identifier !== issue?.identifier && i.parent_id !== issue?.identifier
  )

  // Простой предпросмотр Markdown
  const renderMarkdown = (text) => {
    if (!text) return ''
    return text
      .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold mt-4 mb-2" style="color: var(--color-text)">$1</h3>')
      .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold mt-4 mb-2" style="color: var(--color-text)">$1</h2>')
      .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-4 mb-2" style="color: var(--color-text)">$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code style="background-color: var(--color-bgTertiary); padding: 0.125rem 0.25rem; border-radius: 0.25rem;">$1</code>')
      .replace(/\n/g, '<br/>')
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
    >
      <div
        className="rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col"
        style={{ backgroundColor: 'var(--color-cardBg)' }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between p-4 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <div className="flex items-center space-x-3">
            <span
              className="text-sm"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              {issue?.identifier || 'Новая задача'}
            </span>
            {issue?.issue_type && (
              <span
                className="px-2 py-0.5 text-xs rounded"
                style={{
                  backgroundColor: 'var(--color-bgTertiary)',
                  color: 'var(--color-textSecondary)'
                }}
              >
                {issue.issue_type}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded transition-colors"
            style={{ color: 'var(--color-textSecondary)' }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
          >
            <X className="w-5 h-5" />
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
            placeholder="Название задачи"
            className="w-full bg-transparent text-xl font-semibold border-none outline-none focus:ring-0"
            style={{
              color: 'var(--color-text)'
            }}
          />

          {/* State & Priority Row */}
          <div className="flex items-center space-x-4">
            {/* State Dropdown */}
            <div className="flex-1">
              <label
                className="block text-xs mb-1"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                Статус
              </label>
              <select
                value={formData.state}
                onChange={(e) => handleChange('state', e.target.value)}
                className="w-full rounded-lg px-3 py-2 text-sm border"
                style={{
                  backgroundColor: 'var(--color-inputBg)',
                  borderColor: 'var(--color-inputBorder)',
                  color: 'var(--color-text)'
                }}
              >
                {STATE_OPTIONS.map(option => (
                  <option
                    key={option.value}
                    value={option.value}
                    disabled={!validStates.includes(option.value)}
                  >
                    {option.label} {!validStates.includes(option.value) ? '(недопустимый переход)' : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Priority Dropdown */}
            <div className="flex-1">
              <label
                className="block text-xs mb-1"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                Приоритет
              </label>
              <select
                value={formData.priority}
                onChange={(e) => handleChange('priority', e.target.value)}
                className="w-full rounded-lg px-3 py-2 text-sm border"
                style={{
                  backgroundColor: 'var(--color-inputBg)',
                  borderColor: 'var(--color-inputBorder)',
                  color: 'var(--color-text)'
                }}
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
              <label
                className="text-xs"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                Описание (Markdown)
              </label>
              <button
                onClick={() => setIsPreviewMode(!isPreviewMode)}
                className="text-xs"
                style={{ color: 'var(--color-accent)' }}
              >
                {isPreviewMode ? 'Редактировать' : 'Предпросмотр'}
              </button>
            </div>
            {isPreviewMode ? (
              <div
                className="w-full rounded-lg p-3 min-h-[120px] prose prose-invert prose-sm max-w-none"
                style={{
                  backgroundColor: 'var(--color-bgSecondary)',
                  color: 'var(--color-textSecondary)'
                }}
                dangerouslySetInnerHTML={{ __html: renderMarkdown(formData.description) || '<span style="color: var(--color-textMuted)">Нет описания</span>' }}
              />
            ) : (
              <textarea
                value={formData.description}
                onChange={(e) => handleChange('description', e.target.value)}
                placeholder="Добавьте описание... (поддерживается Markdown)"
                className="w-full rounded-lg px-3 py-2 text-sm border min-h-[120px] resize-y"
                style={{
                  backgroundColor: 'var(--color-inputBg)',
                  borderColor: 'var(--color-inputBorder)',
                  color: 'var(--color-text)'
                }}
              />
            )}
          </div>

          {/* Parent Issue */}
          <div>
            <label
              className="block text-xs mb-1"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              Родительская задача
            </label>
            <select
              value={formData.parent_id || ''}
              onChange={(e) => handleChange('parent_id', e.target.value || null)}
              className="w-full rounded-lg px-3 py-2 text-sm border"
              style={{
                backgroundColor: 'var(--color-inputBg)',
                borderColor: 'var(--color-inputBorder)',
                color: 'var(--color-text)'
              }}
            >
              <option value="">Нет</option>
              {potentialParents.map(i => (
                <option key={i.identifier} value={i.identifier}>
                  {i.identifier}: {i.title}
                </option>
              ))}
            </select>
          </div>

          {/* Dependencies */}
          <div>
            <label
              className="block text-xs mb-1"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              Зависимости
            </label>
            <div className="flex flex-wrap gap-2 mb-2">
              {formData.dependencies.map(dep => (
                <span
                  key={dep}
                  className="inline-flex items-center text-xs px-2 py-1 rounded"
                  style={{
                    backgroundColor: 'var(--color-bgTertiary)',
                    color: 'var(--color-textSecondary)'
                  }}
                >
                  <Link2 className="w-3 h-3 mr-1" />
                  {dep}
                  <button
                    onClick={() => handleChange('dependencies', formData.dependencies.filter(d => d !== dep))}
                    className="ml-1"
                    style={{ color: 'var(--color-textMuted)' }}
                    onMouseEnter={(e) => e.currentTarget.style.color = '#ef4444'}
                    onMouseLeave={(e) => e.currentTarget.style.color = 'var(--color-textMuted)'}
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
              className="w-full rounded-lg px-3 py-2 text-sm border"
              style={{
                backgroundColor: 'var(--color-inputBg)',
                borderColor: 'var(--color-inputBorder)',
                color: 'var(--color-text)'
              }}
            >
              <option value="">Добавить зависимость...</option>
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
              <label
                className="block text-xs mb-2"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                <MessageSquare className="w-3 h-3 inline mr-1" />
                Комментарии ({issue.comments?.length || 0})
              </label>
              <div className="space-y-2 mb-2 max-h-32 overflow-y-auto">
                {(issue.comments || []).map(comment => (
                  <div
                    key={comment.id}
                    className="rounded p-2 text-sm"
                    style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span
                        className="text-xs"
                        style={{ color: 'var(--color-textSecondary)' }}
                      >
                        {comment.author}
                      </span>
                      <span
                        className="text-xs"
                        style={{ color: 'var(--color-textMuted)' }}
                      >
                        {new Date(comment.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p style={{ color: 'var(--color-text)' }}>{comment.content}</p>
                  </div>
                ))}
              </div>
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  placeholder="Добавить комментарий..."
                  className="flex-1 rounded-lg px-3 py-2 text-sm border"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                    color: 'var(--color-text)'
                  }}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddComment()}
                />
                <button
                  onClick={handleAddComment}
                  disabled={!newComment.trim()}
                  className="px-3 py-2 rounded-lg text-sm disabled:opacity-50"
                  style={{
                    backgroundColor: 'var(--color-bgTertiary)',
                    color: 'var(--color-textSecondary)'
                  }}
                >
                  Добавить
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between p-4 border-t"
          style={{
            borderColor: 'var(--color-border)',
            backgroundColor: 'var(--color-bgSecondary)'
          }}
        >
          <div>
            {issue && (
              <button
                onClick={handleDelete}
                className="flex items-center space-x-1 px-3 py-2 rounded-lg text-sm transition-colors"
                style={{
                  backgroundColor: showDeleteConfirm ? '#ef4444' : 'transparent',
                  color: showDeleteConfirm ? 'white' : '#ef4444'
                }}
              >
                <Trash2 className="w-4 h-4" />
                <span>{showDeleteConfirm ? 'Подтвердить удаление' : 'Удалить'}</span>
              </button>
            )}
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={onClose}
              className="px-4 py-2 transition-colors"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              Отмена
            </button>
            <button
              onClick={handleSave}
              disabled={!formData.title.trim()}
              className="flex items-center space-x-1 px-4 py-2 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                backgroundColor: 'var(--color-accent)',
                color: 'white'
              }}
            >
              <Save className="w-4 h-4" />
              <span>Сохранить</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default IssueEditor
