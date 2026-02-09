import React, { useState, useCallback } from 'react'
import { Upload, FileJson, FileSpreadsheet, AlertCircle, CheckCircle, XCircle, Loader2, ExternalLink } from 'lucide-react'

const API_BASE = '/api'

function Import() {
  const [activeTab, setActiveTab] = useState('file') // 'file', 'linear', 'github'
  const [file, setFile] = useState(null)
  const [fileContent, setFileContent] = useState('')
  const [format, setFormat] = useState('json')
  const [preview, setPreview] = useState(null)
  const [importing, setImporting] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [result, setResult] = useState(null)
  const [conflictResolution, setConflictResolution] = useState('skip')
  const [dryRun, setDryRun] = useState(true)

  // GitHub import state
  const [githubOwner, setGithubOwner] = useState('')
  const [githubRepo, setGithubRepo] = useState('')
  const [githubLabels, setGithubLabels] = useState('')
  const [githubState, setGithubState] = useState('open')
  const [importComments, setImportComments] = useState(true)

  const handleFileChange = useCallback((e) => {
    const selectedFile = e.target.files?.[0]
    if (!selectedFile) return

    setFile(selectedFile)
    setPreview(null)
    setResult(null)

    // Auto-detect format
    if (selectedFile.name.endsWith('.csv')) {
      setFormat('csv')
    } else {
      setFormat('json')
    }

    // Read file content
    const reader = new FileReader()
    reader.onload = (event) => {
      setFileContent(event.target?.result || '')
    }
    reader.readAsText(selectedFile)
  }, [])

  const handlePreview = useCallback(async () => {
    if (!fileContent) return

    setPreviewing(true)
    setResult(null)

    try {
      const response = await fetch(`${API_BASE}/import/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          data: fileContent,
          format,
          source: activeTab === 'linear' ? 'linear' : 'generic',
        }),
      })

      const data = await response.json()
      setPreview(data)
    } catch (error) {
      setPreview({ success: false, error: error.message })
    } finally {
      setPreviewing(false)
    }
  }, [fileContent, format, activeTab])

  const handleImport = useCallback(async () => {
    if (!fileContent) return

    setImporting(true)
    setResult(null)

    try {
      const endpoint = activeTab === 'linear' ? '/import/linear' : '/import/execute'
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          data: fileContent,
          format,
          source: activeTab === 'linear' ? 'linear' : 'generic',
          conflict_resolution: conflictResolution,
          dry_run: dryRun,
        }),
      })

      const data = await response.json()
      setResult(data)

      if (data.success && !dryRun) {
        // Clear form on successful real import
        setFile(null)
        setFileContent('')
        setPreview(null)
      }
    } catch (error) {
      setResult({ success: false, error: error.message })
    } finally {
      setImporting(false)
    }
  }, [fileContent, format, activeTab, conflictResolution, dryRun])

  const handleGitHubImport = useCallback(async () => {
    if (!githubOwner || !githubRepo) return

    setImporting(true)
    setResult(null)

    try {
      const response = await fetch(`${API_BASE}/import/github`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          owner: githubOwner,
          repo: githubRepo,
          labels: githubLabels ? githubLabels.split(',').map(l => l.trim()) : null,
          state: githubState,
          import_comments: importComments,
          conflict_resolution: conflictResolution,
        }),
      })

      const data = await response.json()
      setResult(data)
    } catch (error) {
      setResult({ success: false, error: error.message })
    } finally {
      setImporting(false)
    }
  }, [githubOwner, githubRepo, githubLabels, githubState, importComments, conflictResolution])

  const tabs = [
    { id: 'file', label: 'JSON/CSV', icon: FileJson },
    { id: 'linear', label: 'Linear', icon: ExternalLink },
    { id: 'github', label: 'GitHub', icon: ExternalLink },
  ]

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
          Импорт данных
        </h2>
        <p className="mt-1" style={{ color: 'var(--color-textSecondary)' }}>
          Импорт задач из JSON, CSV, Linear или GitHub
        </p>
      </div>

      {/* Tabs */}
      <div
        className="flex space-x-1 p-1 rounded-lg"
        style={{ backgroundColor: 'var(--color-bgSecondary)' }}
      >
        {tabs.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id)
                setPreview(null)
                setResult(null)
              }}
              className="flex items-center space-x-2 px-4 py-2 rounded-md transition-colors flex-1 justify-center"
              style={{
                backgroundColor: isActive ? 'var(--color-accent)' : 'transparent',
                color: isActive ? 'white' : 'var(--color-textSecondary)',
              }}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          )
        })}
      </div>

      {/* File Upload Tab */}
      {(activeTab === 'file' || activeTab === 'linear') && (
        <div
          className="rounded-xl p-6 border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-cardBorder)',
          }}
        >
          <h3
            className="text-lg font-semibold mb-4"
            style={{ color: 'var(--color-text)' }}
          >
            {activeTab === 'linear' ? 'Импорт из экспорта Linear' : 'Загрузить файл'}
          </h3>

          {activeTab === 'linear' && (
            <div
              className="mb-4 p-3 rounded-lg text-sm"
              style={{
                backgroundColor: 'var(--color-bgSecondary)',
                color: 'var(--color-textSecondary)',
              }}
            >
              Экспортируйте данные из Linear (Settings &gt; Workspace &gt; Export) и загрузите JSON-файл сюда.
            </div>
          )}

          {/* Drop Zone */}
          <div
            className="relative border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer"
            style={{
              borderColor: file ? 'var(--color-accent)' : 'var(--color-border)',
              backgroundColor: file ? 'var(--color-accentMuted)' : 'transparent',
            }}
            onClick={() => document.getElementById('file-input')?.click()}
          >
            <input
              id="file-input"
              type="file"
              accept=".json,.csv"
              onChange={handleFileChange}
              className="hidden"
            />

            {file ? (
              <div className="space-y-2">
                <FileJson className="w-12 h-12 mx-auto" style={{ color: 'var(--color-accent)' }} />
                <p className="font-medium" style={{ color: 'var(--color-text)' }}>
                  {file.name}
                </p>
                <p className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Upload className="w-12 h-12 mx-auto" style={{ color: 'var(--color-textMuted)' }} />
                <p className="font-medium" style={{ color: 'var(--color-text)' }}>
                  Перетащите файл сюда или нажмите для выбора
                </p>
                <p className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                  Поддерживаются форматы JSON и CSV
                </p>
              </div>
            )}
          </div>

          {/* Format Selection (for generic file import) */}
          {activeTab === 'file' && file && (
            <div className="mt-4">
              <label
                className="block text-sm font-medium mb-2"
                style={{ color: 'var(--color-text)' }}
              >
                Формат файла
              </label>
              <div className="flex space-x-3">
                {['json', 'csv'].map((fmt) => (
                  <button
                    key={fmt}
                    onClick={() => setFormat(fmt)}
                    className="flex items-center space-x-2 px-4 py-2 rounded-lg border transition-colors"
                    style={{
                      borderColor: format === fmt ? 'var(--color-accent)' : 'var(--color-border)',
                      backgroundColor: format === fmt ? 'var(--color-accentMuted)' : 'transparent',
                      color: 'var(--color-text)',
                    }}
                  >
                    {fmt === 'json' ? <FileJson className="w-4 h-4" /> : <FileSpreadsheet className="w-4 h-4" />}
                    <span className="uppercase">{fmt}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Preview Button */}
          {file && (
            <button
              onClick={handlePreview}
              disabled={previewing}
              className="mt-4 flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors"
              style={{
                backgroundColor: 'var(--color-bgTertiary)',
                color: 'var(--color-text)',
              }}
            >
              {previewing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <FileJson className="w-4 h-4" />
              )}
              <span>Предпросмотр импорта</span>
            </button>
          )}
        </div>
      )}

      {/* GitHub Import Tab */}
      {activeTab === 'github' && (
        <div
          className="rounded-xl p-6 border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-cardBorder)',
          }}
        >
          <h3
            className="text-lg font-semibold mb-4"
            style={{ color: 'var(--color-text)' }}
          >
            Импорт из GitHub
          </h3>

          <div
            className="mb-4 p-3 rounded-lg text-sm"
            style={{
              backgroundColor: 'var(--color-bgSecondary)',
              color: 'var(--color-textSecondary)',
            }}
          >
            Требуется переменная окружения GITHUB_TOKEN на сервере.
          </div>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-text)' }}
                >
                  Владелец/Организация
                </label>
                <input
                  type="text"
                  value={githubOwner}
                  onChange={(e) => setGithubOwner(e.target.value)}
                  placeholder="e.g., facebook"
                  className="w-full px-3 py-2 rounded-lg border text-sm"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                    color: 'var(--color-text)',
                  }}
                />
              </div>
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-text)' }}
                >
                  Репозиторий
                </label>
                <input
                  type="text"
                  value={githubRepo}
                  onChange={(e) => setGithubRepo(e.target.value)}
                  placeholder="e.g., react"
                  className="w-full px-3 py-2 rounded-lg border text-sm"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                    color: 'var(--color-text)',
                  }}
                />
              </div>
            </div>

            <div>
              <label
                className="block text-sm font-medium mb-2"
                style={{ color: 'var(--color-text)' }}
              >
                Фильтр по меткам (через запятую, необязательно)
              </label>
              <input
                type="text"
                value={githubLabels}
                onChange={(e) => setGithubLabels(e.target.value)}
                placeholder="e.g., bug, enhancement"
                className="w-full px-3 py-2 rounded-lg border text-sm"
                style={{
                  backgroundColor: 'var(--color-inputBg)',
                  borderColor: 'var(--color-inputBorder)',
                  color: 'var(--color-text)',
                }}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-text)' }}
                >
                  Статус задач
                </label>
                <select
                  value={githubState}
                  onChange={(e) => setGithubState(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border text-sm"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                    color: 'var(--color-text)',
                  }}
                >
                  <option value="open">Открытые</option>
                  <option value="closed">Закрытые</option>
                  <option value="all">Все</option>
                </select>
              </div>

              <div className="flex items-end">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={importComments}
                    onChange={(e) => setImportComments(e.target.checked)}
                    className="rounded"
                    style={{
                      backgroundColor: 'var(--color-inputBg)',
                      borderColor: 'var(--color-inputBorder)',
                    }}
                  />
                  <span className="text-sm" style={{ color: 'var(--color-text)' }}>
                    Импортировать комментарии
                  </span>
                </label>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Preview Results */}
      {preview && (
        <div
          className="rounded-xl p-6 border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-cardBorder)',
          }}
        >
          <h3
            className="text-lg font-semibold mb-4 flex items-center space-x-2"
            style={{ color: 'var(--color-text)' }}
          >
            {preview.success ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <XCircle className="w-5 h-5 text-red-500" />
            )}
            <span>Результаты предпросмотра</span>
          </h3>

          {preview.success ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div
                  className="p-4 rounded-lg text-center"
                  style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                >
                  <div className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
                    {preview.total_items}
                  </div>
                  <div className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                    Всего записей
                  </div>
                </div>
                <div
                  className="p-4 rounded-lg text-center"
                  style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                >
                  <div className="text-2xl font-bold text-green-500">
                    {preview.new_items}
                  </div>
                  <div className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                    Новых
                  </div>
                </div>
                <div
                  className="p-4 rounded-lg text-center"
                  style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                >
                  <div className="text-2xl font-bold text-yellow-500">
                    {preview.conflicts}
                  </div>
                  <div className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                    Конфликтов
                  </div>
                </div>
              </div>

              {preview.conflict_details?.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2" style={{ color: 'var(--color-text)' }}>
                    Детали конфликтов
                  </h4>
                  <div
                    className="rounded-lg p-3 text-sm space-y-2"
                    style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                  >
                    {preview.conflict_details.map((conflict, idx) => (
                      <div
                        key={idx}
                        className="flex items-center space-x-2"
                        style={{ color: 'var(--color-textSecondary)' }}
                      >
                        <AlertCircle className="w-4 h-4 text-yellow-500 flex-shrink-0" />
                        <span>
                          <strong>{conflict.id}</strong>: "{conflict.existing_title}" vs "{conflict.new_title}"
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {preview.preview?.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2" style={{ color: 'var(--color-text)' }}>
                    Примеры записей
                  </h4>
                  <div
                    className="rounded-lg overflow-hidden border"
                    style={{ borderColor: 'var(--color-border)' }}
                  >
                    <table className="w-full text-sm">
                      <thead>
                        <tr style={{ backgroundColor: 'var(--color-bgSecondary)' }}>
                          <th className="text-left px-3 py-2" style={{ color: 'var(--color-textMuted)' }}>ID</th>
                          <th className="text-left px-3 py-2" style={{ color: 'var(--color-textMuted)' }}>Название</th>
                          <th className="text-left px-3 py-2" style={{ color: 'var(--color-textMuted)' }}>Статус</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.preview.map((item, idx) => (
                          <tr
                            key={idx}
                            className="border-t"
                            style={{ borderColor: 'var(--color-border)' }}
                          >
                            <td className="px-3 py-2" style={{ color: 'var(--color-textSecondary)' }}>
                              {item.identifier}
                            </td>
                            <td className="px-3 py-2" style={{ color: 'var(--color-text)' }}>
                              {item.title?.substring(0, 50)}...
                            </td>
                            <td className="px-3 py-2" style={{ color: 'var(--color-textSecondary)' }}>
                              {item.state}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-red-500">
              {preview.error}
            </div>
          )}
        </div>
      )}

      {/* Import Options */}
      {(preview?.success || activeTab === 'github') && (
        <div
          className="rounded-xl p-6 border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-cardBorder)',
          }}
        >
          <h3
            className="text-lg font-semibold mb-4"
            style={{ color: 'var(--color-text)' }}
          >
            Параметры импорта
          </h3>

          <div className="space-y-4">
            <div>
              <label
                className="block text-sm font-medium mb-2"
                style={{ color: 'var(--color-text)' }}
              >
                Разрешение конфликтов
              </label>
              <div className="flex space-x-3">
                {[
                  { id: 'skip', label: 'Пропустить существующие' },
                  { id: 'update', label: 'Обновить существующие' },
                  { id: 'duplicate', label: 'Создать дубликаты' },
                ].map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setConflictResolution(option.id)}
                    className="px-4 py-2 rounded-lg border transition-colors text-sm"
                    style={{
                      borderColor: conflictResolution === option.id ? 'var(--color-accent)' : 'var(--color-border)',
                      backgroundColor: conflictResolution === option.id ? 'var(--color-accentMuted)' : 'transparent',
                      color: 'var(--color-text)',
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {activeTab !== 'github' && (
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="dry-run"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  className="rounded"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                  }}
                />
                <label
                  htmlFor="dry-run"
                  className="text-sm cursor-pointer"
                  style={{ color: 'var(--color-text)' }}
                >
                  Пробный запуск (только предпросмотр, без импорта)
                </label>
              </div>
            )}

            <button
              onClick={activeTab === 'github' ? handleGitHubImport : handleImport}
              disabled={importing || (activeTab === 'github' ? (!githubOwner || !githubRepo) : !fileContent)}
              className="flex items-center space-x-2 px-6 py-3 rounded-lg transition-colors disabled:opacity-50"
              style={{
                backgroundColor: 'var(--color-accent)',
                color: 'white',
              }}
            >
              {importing ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Upload className="w-5 h-5" />
              )}
              <span>
                {dryRun && activeTab !== 'github' ? 'Предпросмотр импорта' : 'Импортировать'}
              </span>
            </button>
          </div>
        </div>
      )}

      {/* Import Results */}
      {result && (
        <div
          className="rounded-xl p-6 border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: result.success ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)',
          }}
        >
          <h3
            className="text-lg font-semibold mb-4 flex items-center space-x-2"
            style={{ color: 'var(--color-text)' }}
          >
            {result.success ? (
              <CheckCircle className="w-5 h-5 text-green-500" />
            ) : (
              <XCircle className="w-5 h-5 text-red-500" />
            )}
            <span>
              {result.success
                ? (result.dry_run ? 'Пробный запуск завершён' : 'Импорт завершён')
                : 'Ошибка импорта'}
            </span>
          </h3>

          {result.success ? (
            <div className="space-y-4">
              {result.dry_run && (
                <div
                  className="p-3 rounded-lg text-sm"
                  style={{
                    backgroundColor: 'rgba(234, 179, 8, 0.1)',
                    color: 'rgb(234, 179, 8)',
                  }}
                >
                  Это был пробный запуск. Данные не были импортированы.
                </div>
              )}

              <div className="grid grid-cols-4 gap-4">
                <div
                  className="p-4 rounded-lg text-center"
                  style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                >
                  <div className="text-2xl font-bold text-green-500">
                    {result.results?.created || 0}
                  </div>
                  <div className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                    Создано
                  </div>
                </div>
                <div
                  className="p-4 rounded-lg text-center"
                  style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                >
                  <div className="text-2xl font-bold text-blue-500">
                    {result.results?.updated || 0}
                  </div>
                  <div className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                    Обновлено
                  </div>
                </div>
                <div
                  className="p-4 rounded-lg text-center"
                  style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                >
                  <div className="text-2xl font-bold text-yellow-500">
                    {result.results?.skipped || 0}
                  </div>
                  <div className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                    Пропущено
                  </div>
                </div>
                <div
                  className="p-4 rounded-lg text-center"
                  style={{ backgroundColor: 'var(--color-bgSecondary)' }}
                >
                  <div className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
                    {result.total_issues_after || 0}
                  </div>
                  <div className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                    Всего задач
                  </div>
                </div>
              </div>

              {result.results?.errors?.length > 0 && (
                <div>
                  <h4 className="font-medium mb-2 text-red-500">Ошибки</h4>
                  <div
                    className="rounded-lg p-3 text-sm space-y-1"
                    style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)' }}
                  >
                    {result.results.errors.map((err, idx) => (
                      <div key={idx} style={{ color: 'rgb(239, 68, 68)' }}>
                        {err.id || err.linear_id || err.github_number}: {err.error}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-red-500">
              {result.error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default Import
