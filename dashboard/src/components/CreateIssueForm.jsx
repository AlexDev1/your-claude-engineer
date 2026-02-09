import React, { useState, useRef, useEffect } from 'react'
import { Plus, X, Bug, Lightbulb, CheckSquare, Layers } from 'lucide-react'

const ISSUE_TEMPLATES = [
  {
    type: 'Bug',
    icon: Bug,
    color: '#ef4444',
    description: 'Что-то сломано',
    defaults: {
      priority: 'high',
      description: '## Bug Description\n\n## Steps to Reproduce\n1. \n\n## Expected Behavior\n\n## Actual Behavior\n\n## Environment\n',
    },
  },
  {
    type: 'Feature',
    icon: Lightbulb,
    color: '#3b82f6',
    description: 'Новая функциональность',
    defaults: {
      priority: 'medium',
      description: '## Feature Description\n\n## User Story\nAs a [user], I want [feature] so that [benefit].\n\n## Acceptance Criteria\n- [ ] \n\n## Technical Notes\n',
    },
  },
  {
    type: 'Task',
    icon: CheckSquare,
    color: '#6b7280',
    description: 'Общая рабочая задача',
    defaults: {
      priority: 'medium',
      description: '## Task Description\n\n## Requirements\n- \n\n## Notes\n',
    },
  },
  {
    type: 'Epic',
    icon: Layers,
    color: '#a855f7',
    description: 'Контейнер для крупной функции',
    defaults: {
      priority: 'medium',
      description: '## Epic Overview\n\n## Goals\n- \n\n## Sub-tasks\n- [ ] \n\n## Success Metrics\n',
    },
  },
]

const PRIORITY_OPTIONS = [
  { value: 'urgent', label: 'Срочный' },
  { value: 'high', label: 'Высокий' },
  { value: 'medium', label: 'Средний' },
  { value: 'low', label: 'Низкий' },
]

const TEAM_OPTIONS = ['ENG', 'DESIGN', 'PRODUCT', 'OPS']
const PROJECT_OPTIONS = ['Agent Dashboard', 'Core Platform', 'Infrastructure', 'Documentation']

function CreateIssueForm({ isOpen, onClose, onCreate, allIssues = [] }) {
  const [step, setStep] = useState('template') // 'template' | 'form'
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    priority: 'medium',
    issue_type: 'Task',
    team: 'ENG',
    project: null,
    parent_id: null,
    dependencies: [],
  })
  const titleRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      setStep('template')
      setSelectedTemplate(null)
      setFormData({
        title: '',
        description: '',
        priority: 'medium',
        issue_type: 'Task',
        team: 'ENG',
        project: null,
        parent_id: null,
        dependencies: [],
      })
    }
  }, [isOpen])

  useEffect(() => {
    if (step === 'form' && titleRef.current) {
      titleRef.current.focus()
    }
  }, [step])

  if (!isOpen) return null

  const handleTemplateSelect = (template) => {
    setSelectedTemplate(template)
    setFormData(prev => ({
      ...prev,
      issue_type: template.type,
      priority: template.defaults.priority,
      description: template.defaults.description,
    }))
    setStep('form')
  }

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!formData.title.trim()) return

    onCreate(formData)
    onClose()
  }

  const potentialParents = allIssues.filter(i => i.issue_type === 'Epic' || !i.parent_id)

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
    >
      <div
        className="rounded-xl w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col"
        style={{ backgroundColor: 'var(--color-cardBg)' }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between p-4 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <h2
            className="text-lg font-semibold"
            style={{ color: 'var(--color-text)' }}
          >
            {step === 'template' ? 'Создать задачу' : `Новый ${formData.issue_type}`}
          </h2>
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

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {step === 'template' ? (
            <div className="space-y-3">
              <p
                className="text-sm mb-4"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                Выберите шаблон для начала:
              </p>
              <div className="grid grid-cols-2 gap-3">
                {ISSUE_TEMPLATES.map(template => {
                  const Icon = template.icon
                  return (
                    <button
                      key={template.type}
                      onClick={() => handleTemplateSelect(template)}
                      className="flex flex-col items-center p-4 border rounded-lg transition-all group"
                      style={{
                        backgroundColor: 'var(--color-bgSecondary)',
                        borderColor: 'var(--color-border)'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'
                        e.currentTarget.style.borderColor = template.color
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'var(--color-bgSecondary)'
                        e.currentTarget.style.borderColor = 'var(--color-border)'
                      }}
                    >
                      <div
                        className="p-2 rounded-lg mb-2"
                        style={{ backgroundColor: template.color }}
                      >
                        <Icon className="w-5 h-5 text-white" />
                      </div>
                      <span
                        className="font-medium"
                        style={{ color: 'var(--color-text)' }}
                      >
                        {template.type}
                      </span>
                      <span
                        className="text-xs mt-1"
                        style={{ color: 'var(--color-textSecondary)' }}
                      >
                        {template.description}
                      </span>
                    </button>
                  )
                })}
              </div>
              <button
                onClick={() => {
                  setSelectedTemplate(null)
                  setFormData(prev => ({ ...prev, issue_type: 'Task' }))
                  setStep('form')
                }}
                className="w-full mt-4 text-sm transition-colors"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                Пропустить шаблон, создать пустую задачу
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Title */}
              <div>
                <label
                  className="block text-xs mb-1"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  Название *
                </label>
                <input
                  ref={titleRef}
                  type="text"
                  value={formData.title}
                  onChange={(e) => handleChange('title', e.target.value)}
                  placeholder="Название задачи"
                  required
                  className="w-full rounded-lg px-3 py-2 text-sm border"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                    color: 'var(--color-text)'
                  }}
                />
              </div>

              {/* Team & Project Row */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label
                    className="block text-xs mb-1"
                    style={{ color: 'var(--color-textSecondary)' }}
                  >
                    Команда
                  </label>
                  <select
                    value={formData.team}
                    onChange={(e) => handleChange('team', e.target.value)}
                    className="w-full rounded-lg px-3 py-2 text-sm border"
                    style={{
                      backgroundColor: 'var(--color-inputBg)',
                      borderColor: 'var(--color-inputBorder)',
                      color: 'var(--color-text)'
                    }}
                  >
                    {TEAM_OPTIONS.map(team => (
                      <option key={team} value={team}>{team}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label
                    className="block text-xs mb-1"
                    style={{ color: 'var(--color-textSecondary)' }}
                  >
                    Проект
                  </label>
                  <select
                    value={formData.project || ''}
                    onChange={(e) => handleChange('project', e.target.value || null)}
                    className="w-full rounded-lg px-3 py-2 text-sm border"
                    style={{
                      backgroundColor: 'var(--color-inputBg)',
                      borderColor: 'var(--color-inputBorder)',
                      color: 'var(--color-text)'
                    }}
                  >
                    <option value="">Нет</option>
                    {PROJECT_OPTIONS.map(project => (
                      <option key={project} value={project}>{project}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Priority */}
              <div>
                <label
                  className="block text-xs mb-1"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  Приоритет
                </label>
                <div className="flex space-x-2">
                  {PRIORITY_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => handleChange('priority', option.value)}
                      className="flex-1 py-2 px-3 text-sm rounded-lg border transition-colors"
                      style={{
                        borderColor: formData.priority === option.value ? 'var(--color-accent)' : 'var(--color-border)',
                        backgroundColor: formData.priority === option.value ? 'rgba(96, 165, 250, 0.2)' : 'var(--color-inputBg)',
                        color: formData.priority === option.value ? 'var(--color-text)' : 'var(--color-textSecondary)'
                      }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div>
                <label
                  className="block text-xs mb-1"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  Описание (Markdown)
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => handleChange('description', e.target.value)}
                  placeholder="Добавьте описание..."
                  className="w-full rounded-lg px-3 py-2 text-sm border min-h-[120px] resize-y font-mono"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                    color: 'var(--color-text)'
                  }}
                />
              </div>

              {/* Parent Issue */}
              <div>
                <label
                  className="block text-xs mb-1"
                  style={{ color: 'var(--color-textSecondary)' }}
                >
                  Родительская задача (необязательно)
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
                  Зависимости (необязательно)
                </label>
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
                  {allIssues
                    .filter(i => !formData.dependencies.includes(i.identifier))
                    .map(i => (
                      <option key={i.identifier} value={i.identifier}>
                        {i.identifier}: {i.title}
                      </option>
                    ))}
                </select>
                {formData.dependencies.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {formData.dependencies.map(dep => (
                      <span
                        key={dep}
                        className="inline-flex items-center text-xs px-2 py-1 rounded"
                        style={{
                          backgroundColor: 'var(--color-bgTertiary)',
                          color: 'var(--color-textSecondary)'
                        }}
                      >
                        {dep}
                        <button
                          type="button"
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
                )}
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        {step === 'form' && (
          <div
            className="flex items-center justify-between p-4 border-t"
            style={{
              borderColor: 'var(--color-border)',
              backgroundColor: 'var(--color-bgSecondary)'
            }}
          >
            <button
              onClick={() => setStep('template')}
              className="text-sm transition-colors"
              style={{ color: 'var(--color-textSecondary)' }}
            >
              Назад к шаблонам
            </button>
            <div className="flex items-center space-x-2">
              <button
                onClick={onClose}
                className="px-4 py-2 transition-colors"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                Отмена
              </button>
              <button
                onClick={handleSubmit}
                disabled={!formData.title.trim()}
                className="flex items-center space-x-1 px-4 py-2 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  backgroundColor: 'var(--color-accent)',
                  color: 'white'
                }}
              >
                <Plus className="w-4 h-4" />
                <span>Создать задачу</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default CreateIssueForm
