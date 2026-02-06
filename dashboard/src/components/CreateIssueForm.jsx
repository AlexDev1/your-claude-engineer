import React, { useState, useRef, useEffect } from 'react'
import { Plus, X, Bug, Lightbulb, CheckSquare, Layers } from 'lucide-react'

const ISSUE_TEMPLATES = [
  {
    type: 'Bug',
    icon: Bug,
    color: 'bg-red-500',
    description: 'Something is broken',
    defaults: {
      priority: 'high',
      description: '## Bug Description\n\n## Steps to Reproduce\n1. \n\n## Expected Behavior\n\n## Actual Behavior\n\n## Environment\n',
    },
  },
  {
    type: 'Feature',
    icon: Lightbulb,
    color: 'bg-blue-500',
    description: 'New functionality',
    defaults: {
      priority: 'medium',
      description: '## Feature Description\n\n## User Story\nAs a [user], I want [feature] so that [benefit].\n\n## Acceptance Criteria\n- [ ] \n\n## Technical Notes\n',
    },
  },
  {
    type: 'Task',
    icon: CheckSquare,
    color: 'bg-gray-500',
    description: 'General work item',
    defaults: {
      priority: 'medium',
      description: '## Task Description\n\n## Requirements\n- \n\n## Notes\n',
    },
  },
  {
    type: 'Epic',
    icon: Layers,
    color: 'bg-purple-500',
    description: 'Large feature container',
    defaults: {
      priority: 'medium',
      description: '## Epic Overview\n\n## Goals\n- \n\n## Sub-tasks\n- [ ] \n\n## Success Metrics\n',
    },
  },
]

const PRIORITY_OPTIONS = [
  { value: 'urgent', label: 'Urgent' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
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
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white">
            {step === 'template' ? 'Create New Issue' : `New ${formData.issue_type}`}
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {step === 'template' ? (
            <div className="space-y-3">
              <p className="text-gray-400 text-sm mb-4">Choose a template to get started:</p>
              <div className="grid grid-cols-2 gap-3">
                {ISSUE_TEMPLATES.map(template => {
                  const Icon = template.icon
                  return (
                    <button
                      key={template.type}
                      onClick={() => handleTemplateSelect(template)}
                      className="flex flex-col items-center p-4 bg-gray-700/50 hover:bg-gray-700 border border-gray-600 hover:border-gray-500 rounded-lg transition-all group"
                    >
                      <div className={`p-2 rounded-lg ${template.color} mb-2`}>
                        <Icon className="w-5 h-5 text-white" />
                      </div>
                      <span className="text-white font-medium">{template.type}</span>
                      <span className="text-gray-400 text-xs mt-1">{template.description}</span>
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
                className="w-full mt-4 text-sm text-gray-400 hover:text-white transition-colors"
              >
                Skip template, create blank issue
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Title */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Title *</label>
                <input
                  ref={titleRef}
                  type="text"
                  value={formData.title}
                  onChange={(e) => handleChange('title', e.target.value)}
                  placeholder="Issue title"
                  required
                  className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                />
              </div>

              {/* Team & Project Row */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Team</label>
                  <select
                    value={formData.team}
                    onChange={(e) => handleChange('team', e.target.value)}
                    className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500"
                  >
                    {TEAM_OPTIONS.map(team => (
                      <option key={team} value={team}>{team}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Project</label>
                  <select
                    value={formData.project || ''}
                    onChange={(e) => handleChange('project', e.target.value || null)}
                    className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500"
                  >
                    <option value="">None</option>
                    {PROJECT_OPTIONS.map(project => (
                      <option key={project} value={project}>{project}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Priority */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Priority</label>
                <div className="flex space-x-2">
                  {PRIORITY_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => handleChange('priority', option.value)}
                      className={`flex-1 py-2 px-3 text-sm rounded-lg border transition-colors ${
                        formData.priority === option.value
                          ? 'border-blue-500 bg-blue-500/20 text-white'
                          : 'border-gray-600 bg-gray-700 text-gray-300 hover:border-gray-500'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Description (Markdown)</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => handleChange('description', e.target.value)}
                  placeholder="Add a description..."
                  className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500 min-h-[120px] resize-y font-mono"
                />
              </div>

              {/* Parent Issue */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">Parent Issue (Optional)</label>
                <select
                  value={formData.parent_id || ''}
                  onChange={(e) => handleChange('parent_id', e.target.value || null)}
                  className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500"
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
                <label className="block text-xs text-gray-400 mb-1">Dependencies (Optional)</label>
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value && !formData.dependencies.includes(e.target.value)) {
                      handleChange('dependencies', [...formData.dependencies, e.target.value])
                    }
                  }}
                  className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm border border-gray-600 focus:border-blue-500"
                >
                  <option value="">Add dependency...</option>
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
                        className="inline-flex items-center bg-gray-700 text-gray-300 text-xs px-2 py-1 rounded"
                      >
                        {dep}
                        <button
                          type="button"
                          onClick={() => handleChange('dependencies', formData.dependencies.filter(d => d !== dep))}
                          className="ml-1 hover:text-red-400"
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
          <div className="flex items-center justify-between p-4 border-t border-gray-700 bg-gray-800/80">
            <button
              onClick={() => setStep('template')}
              className="text-gray-400 hover:text-white text-sm transition-colors"
            >
              Back to templates
            </button>
            <div className="flex items-center space-x-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={!formData.title.trim()}
                className="flex items-center space-x-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus className="w-4 h-4" />
                <span>Create Issue</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default CreateIssueForm
