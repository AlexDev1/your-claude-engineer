import React, { useState, useEffect, useCallback } from 'react'
import {
  Download, FileJson, FileSpreadsheet, FileText, Loader2, CheckCircle,
  Archive, Trash2, RotateCcw, Clock, HardDrive, AlertCircle
} from 'lucide-react'

const API_BASE = '/api'

function Export() {
  const [activeTab, setActiveTab] = useState('export') // 'export', 'backups'
  const [exporting, setExporting] = useState(false)
  const [exportResult, setExportResult] = useState(null)
  const [backups, setBackups] = useState([])
  const [loadingBackups, setLoadingBackups] = useState(false)
  const [creatingBackup, setCreatingBackup] = useState(false)
  const [restoringBackup, setRestoringBackup] = useState(null)
  const [backupMessage, setBackupMessage] = useState(null)

  // Export options
  const [includeComments, setIncludeComments] = useState(true)
  const [team, setTeam] = useState('ENG')

  const fetchBackups = useCallback(async () => {
    setLoadingBackups(true)
    try {
      const response = await fetch(`${API_BASE}/backups`)
      const data = await response.json()
      setBackups(data.backups || [])
    } catch (error) {
      console.error('Failed to fetch backups:', error)
    } finally {
      setLoadingBackups(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'backups') {
      fetchBackups()
    }
  }, [activeTab, fetchBackups])

  const handleExportJSON = useCallback(async () => {
    setExporting(true)
    setExportResult(null)

    try {
      const response = await fetch(
        `${API_BASE}/export/json?team=${team}&include_comments=${includeComments}`
      )
      const data = await response.json()

      // Create download
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `issues_${team}_${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      setExportResult({
        success: true,
        format: 'JSON',
        issueCount: data.issue_count,
      })
    } catch (error) {
      setExportResult({ success: false, error: error.message })
    } finally {
      setExporting(false)
    }
  }, [team, includeComments])

  const handleExportCSV = useCallback(async () => {
    setExporting(true)
    setExportResult(null)

    try {
      const response = await fetch(`${API_BASE}/export/csv?team=${team}`)
      const blob = await response.blob()

      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `issues_${team}_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      setExportResult({
        success: true,
        format: 'CSV',
      })
    } catch (error) {
      setExportResult({ success: false, error: error.message })
    } finally {
      setExporting(false)
    }
  }, [team])

  const handleExportMarkdown = useCallback(async () => {
    setExporting(true)
    setExportResult(null)

    try {
      const response = await fetch(`${API_BASE}/export/markdown?team=${team}`)
      const data = await response.json()

      // Create a zip-like download (using JSON for simplicity)
      // In a real app, you'd use JSZip to create actual zip
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `issues_markdown_${team}_${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      setExportResult({
        success: true,
        format: 'Markdown',
        fileCount: data.file_count,
      })
    } catch (error) {
      setExportResult({ success: false, error: error.message })
    } finally {
      setExporting(false)
    }
  }, [team])

  const handleCreateBackup = useCallback(async () => {
    setCreatingBackup(true)
    setBackupMessage(null)

    try {
      const response = await fetch(`${API_BASE}/backups/create`, { method: 'POST' })
      const data = await response.json()

      if (data.success) {
        setBackupMessage({ type: 'success', text: `Backup created: ${data.backup.filename}` })
        fetchBackups()
      } else {
        setBackupMessage({ type: 'error', text: data.error || 'Failed to create backup' })
      }
    } catch (error) {
      setBackupMessage({ type: 'error', text: error.message })
    } finally {
      setCreatingBackup(false)
    }
  }, [fetchBackups])

  const handleRestoreBackup = useCallback(async (filename) => {
    if (!confirm(`Вы уверены, что хотите восстановить из ${filename}? Это заменит все текущие задачи.`)) {
      return
    }

    setRestoringBackup(filename)
    setBackupMessage(null)

    try {
      const response = await fetch(`${API_BASE}/backups/restore/${filename}`, { method: 'POST' })
      const data = await response.json()

      if (data.success) {
        setBackupMessage({
          type: 'success',
          text: `Restored ${data.restored_issues} issues from backup (${data.backup_date})`,
        })
      } else {
        setBackupMessage({ type: 'error', text: data.error || 'Failed to restore backup' })
      }
    } catch (error) {
      setBackupMessage({ type: 'error', text: error.message })
    } finally {
      setRestoringBackup(null)
    }
  }, [])

  const handleDeleteBackup = useCallback(async (filename) => {
    if (!confirm(`Вы уверены, что хотите удалить ${filename}?`)) {
      return
    }

    try {
      const response = await fetch(`${API_BASE}/backups/${filename}`, { method: 'DELETE' })
      const data = await response.json()

      if (data.success) {
        setBackupMessage({ type: 'success', text: `Deleted ${filename}` })
        fetchBackups()
      } else {
        setBackupMessage({ type: 'error', text: data.error || 'Failed to delete backup' })
      }
    } catch (error) {
      setBackupMessage({ type: 'error', text: error.message })
    }
  }, [fetchBackups])

  const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (isoString) => {
    const date = new Date(isoString)
    return date.toLocaleString()
  }

  const exportOptions = [
    {
      id: 'json',
      label: 'Экспорт JSON',
      description: 'Полный экспорт со всеми данными, комментариями и метаданными',
      icon: FileJson,
      action: handleExportJSON,
      color: '#3b82f6',
    },
    {
      id: 'csv',
      label: 'Экспорт CSV',
      description: 'Упрощённый формат для Excel/Google Sheets (id, title, state, priority, created_at)',
      icon: FileSpreadsheet,
      action: handleExportCSV,
      color: '#22c55e',
    },
    {
      id: 'markdown',
      label: 'Экспорт Markdown',
      description: 'Каждая задача как отдельный .md файл (экспортируется как JSON-пакет)',
      icon: FileText,
      action: handleExportMarkdown,
      color: '#a855f7',
    },
  ]

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>
          Экспорт и резервные копии
        </h2>
        <p className="mt-1" style={{ color: 'var(--color-textSecondary)' }}>
          Экспорт данных и управление резервными копиями
        </p>
      </div>

      {/* Tabs */}
      <div
        className="flex space-x-1 p-1 rounded-lg"
        style={{ backgroundColor: 'var(--color-bgSecondary)' }}
      >
        {[
          { id: 'export', label: 'Экспорт данных', icon: Download },
          { id: 'backups', label: 'Резервные копии', icon: Archive },
        ].map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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

      {/* Export Tab */}
      {activeTab === 'export' && (
        <>
          {/* Export Options */}
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
              Параметры экспорта
            </h3>

            <div className="grid grid-cols-2 gap-4 mb-6">
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-text)' }}
                >
                  Команда
                </label>
                <select
                  value={team}
                  onChange={(e) => setTeam(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border text-sm"
                  style={{
                    backgroundColor: 'var(--color-inputBg)',
                    borderColor: 'var(--color-inputBorder)',
                    color: 'var(--color-text)',
                  }}
                >
                  <option value="ENG">ENG</option>
                  <option value="DESIGN">DESIGN</option>
                  <option value="PRODUCT">PRODUCT</option>
                </select>
              </div>

              <div className="flex items-end">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeComments}
                    onChange={(e) => setIncludeComments(e.target.checked)}
                    className="rounded"
                    style={{
                      backgroundColor: 'var(--color-inputBg)',
                      borderColor: 'var(--color-inputBorder)',
                    }}
                  />
                  <span className="text-sm" style={{ color: 'var(--color-text)' }}>
                    Включить комментарии (только JSON)
                  </span>
                </label>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {exportOptions.map((option) => {
                const Icon = option.icon
                return (
                  <button
                    key={option.id}
                    onClick={option.action}
                    disabled={exporting}
                    className="flex flex-col items-center p-6 rounded-lg border-2 transition-all hover:scale-[1.02] disabled:opacity-50"
                    style={{
                      borderColor: 'var(--color-border)',
                      backgroundColor: 'var(--color-bgSecondary)',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = option.color
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = 'var(--color-border)'
                    }}
                  >
                    <div
                      className="w-12 h-12 rounded-full flex items-center justify-center mb-3"
                      style={{ backgroundColor: `${option.color}20` }}
                    >
                      {exporting ? (
                        <Loader2 className="w-6 h-6 animate-spin" style={{ color: option.color }} />
                      ) : (
                        <Icon className="w-6 h-6" style={{ color: option.color }} />
                      )}
                    </div>
                    <span
                      className="font-medium mb-1"
                      style={{ color: 'var(--color-text)' }}
                    >
                      {option.label}
                    </span>
                    <span
                      className="text-xs text-center"
                      style={{ color: 'var(--color-textSecondary)' }}
                    >
                      {option.description}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Export Result */}
          {exportResult && (
            <div
              className="rounded-xl p-4 border flex items-center space-x-3"
              style={{
                backgroundColor: 'var(--color-cardBg)',
                borderColor: exportResult.success ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)',
              }}
            >
              {exportResult.success ? (
                <>
                  <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />
                  <div>
                    <p className="font-medium" style={{ color: 'var(--color-text)' }}>
                      {exportResult.format} экспорт завершён
                    </p>
                    <p className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                      {exportResult.issueCount && `${exportResult.issueCount} задач экспортировано`}
                      {exportResult.fileCount && `${exportResult.fileCount} файлов экспортировано`}
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                  <div>
                    <p className="font-medium text-red-500">Ошибка экспорта</p>
                    <p className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                      {exportResult.error}
                    </p>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      {/* Backups Tab */}
      {activeTab === 'backups' && (
        <>
          {/* Backup Actions */}
          <div
            className="rounded-xl p-6 border"
            style={{
              backgroundColor: 'var(--color-cardBg)',
              borderColor: 'var(--color-cardBorder)',
            }}
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3
                  className="text-lg font-semibold"
                  style={{ color: 'var(--color-text)' }}
                >
                  Управление копиями
                </h3>
                <p className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
                  Создание и восстановление резервных копий данных задач
                </p>
              </div>

              <button
                onClick={handleCreateBackup}
                disabled={creatingBackup}
                className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors"
                style={{
                  backgroundColor: 'var(--color-accent)',
                  color: 'white',
                }}
              >
                {creatingBackup ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Archive className="w-4 h-4" />
                )}
                <span>Создать копию</span>
              </button>
            </div>

            {/* Backup Message */}
            {backupMessage && (
              <div
                className="mb-4 p-3 rounded-lg flex items-center space-x-2"
                style={{
                  backgroundColor: backupMessage.type === 'success'
                    ? 'rgba(34, 197, 94, 0.1)'
                    : 'rgba(239, 68, 68, 0.1)',
                }}
              >
                {backupMessage.type === 'success' ? (
                  <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                )}
                <span
                  style={{
                    color: backupMessage.type === 'success' ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)',
                  }}
                >
                  {backupMessage.text}
                </span>
              </div>
            )}

            {/* Backup List */}
            {loadingBackups ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--color-textMuted)' }} />
              </div>
            ) : backups.length === 0 ? (
              <div
                className="text-center py-8"
                style={{ color: 'var(--color-textSecondary)' }}
              >
                <Archive className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Копий пока нет</p>
                <p className="text-sm">Создайте первую копию для защиты данных</p>
              </div>
            ) : (
              <div className="space-y-3">
                {backups.map((backup) => (
                  <div
                    key={backup.filename}
                    className="flex items-center justify-between p-4 rounded-lg border"
                    style={{
                      backgroundColor: 'var(--color-bgSecondary)',
                      borderColor: 'var(--color-border)',
                    }}
                  >
                    <div className="flex items-center space-x-4">
                      <div
                        className="w-10 h-10 rounded-lg flex items-center justify-center"
                        style={{ backgroundColor: 'var(--color-bgTertiary)' }}
                      >
                        <FileJson className="w-5 h-5" style={{ color: 'var(--color-textMuted)' }} />
                      </div>
                      <div>
                        <p className="font-medium" style={{ color: 'var(--color-text)' }}>
                          {backup.filename}
                        </p>
                        <div
                          className="flex items-center space-x-4 text-sm"
                          style={{ color: 'var(--color-textSecondary)' }}
                        >
                          <span className="flex items-center space-x-1">
                            <Clock className="w-3 h-3" />
                            <span>{formatDate(backup.created_at)}</span>
                          </span>
                          <span className="flex items-center space-x-1">
                            <HardDrive className="w-3 h-3" />
                            <span>{formatBytes(backup.size_bytes)}</span>
                          </span>
                          <span>{backup.issue_count} задач</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleRestoreBackup(backup.filename)}
                        disabled={restoringBackup === backup.filename}
                        className="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-sm transition-colors"
                        style={{
                          backgroundColor: 'var(--color-bgTertiary)',
                          color: 'var(--color-text)',
                        }}
                        title="Восстановить из этой копии"
                      >
                        {restoringBackup === backup.filename ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RotateCcw className="w-4 h-4" />
                        )}
                        <span>Восстановить</span>
                      </button>
                      <button
                        onClick={() => handleDeleteBackup(backup.filename)}
                        className="p-1.5 rounded-lg transition-colors hover:bg-red-100"
                        style={{ color: 'var(--color-textMuted)' }}
                        title="Удалить копию"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Scheduled Backup Info */}
          <div
            className="rounded-xl p-4 border"
            style={{
              backgroundColor: 'var(--color-bgSecondary)',
              borderColor: 'var(--color-border)',
            }}
          >
            <h4 className="font-medium mb-2" style={{ color: 'var(--color-text)' }}>
              Автоматические копии
            </h4>
            <p className="text-sm" style={{ color: 'var(--color-textSecondary)' }}>
              Автоматические ежедневные копии можно включить через cron-задачу.
              Копии хранятся в каталоге <code className="px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--color-bgTertiary)' }}>backups/</code>
              с хранением 30 дней.
            </p>
            <div
              className="mt-3 p-2 rounded text-xs font-mono"
              style={{
                backgroundColor: 'var(--color-bgTertiary)',
                color: 'var(--color-textSecondary)',
              }}
            >
              # Add to crontab for daily backups at 2 AM<br />
              0 2 * * * cd /path/to/project && python scripts/backup.py
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default Export
