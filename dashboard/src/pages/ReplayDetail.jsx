import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  RefreshCw,
  FileCode,
  Terminal,
  MessageSquare,
  ChevronRight,
  Hash,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
} from 'lucide-react'
import { useSessionDetail } from '../hooks/useSessions'
import TimelineSlider from '../components/TimelineSlider'
import DiffViewer from '../components/DiffViewer'

/** Map status values to display colors */
const STATUS_COLORS = {
  completed: '#22c55e',
  failed: '#ef4444',
  running: '#3b82f6',
  unknown: '#6b7280',
}

/** Map event type to display-friendly label and icon */
const EVENT_TYPE_CONFIG = {
  tool_call: { label: 'Вызов инструмента', icon: Terminal, color: '#8b5cf6' },
  file_write: { label: 'Запись файла', icon: FileCode, color: '#22c55e' },
  bash: { label: 'Bash', icon: Terminal, color: '#f59e0b' },
  agent_call: { label: 'Вызов агента', icon: MessageSquare, color: '#3b82f6' },
}

/** Playback timer interval in milliseconds */
const PLAYBACK_INTERVAL_MS = 100

/**
 * Format seconds to a MM:SS or HH:MM:SS string.
 *
 * @param {number} totalSeconds - Duration in seconds
 * @returns {string} Formatted time string
 */
function formatTime(totalSeconds) {
  const abs = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(abs / 3600)
  const m = Math.floor((abs % 3600) / 60)
  const s = abs % 60
  const pad = (n) => String(n).padStart(2, '0')
  if (h > 0) return `${pad(h)}:${pad(m)}:${pad(s)}`
  return `${pad(m)}:${pad(s)}`
}

/**
 * Extract the list of unique file paths from session events.
 *
 * @param {Array} events - Session event objects
 * @returns {Array<string>} Sorted unique file paths
 */
function extractAffectedFiles(events) {
  const files = new Set()
  for (const event of events) {
    const data = event.data || {}
    if (data.file_path) {
      files.add(data.file_path)
    }
    if (data.arguments?.file_path) {
      files.add(data.arguments.file_path)
    }
  }
  return [...files].sort()
}

/**
 * FileListPanel displays files affected by the session and allows selecting one.
 *
 * @param {Object} props
 * @param {Array<string>} props.files - List of file paths
 * @param {string|null} props.selectedFile - Currently selected file path
 * @param {function} props.onSelect - Callback when a file is selected
 */
function FileListPanel({ files, selectedFile, onSelect }) {
  if (files.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-full"
        style={{ color: 'var(--color-textMuted)' }}
      >
        <span className="text-sm">Файлы не изменены</span>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {files.map((filePath) => {
        const isActive = filePath === selectedFile
        const fileName = filePath.split('/').pop()
        const dirPath = filePath.split('/').slice(0, -1).join('/')

        return (
          <button
            key={filePath}
            onClick={() => onSelect(filePath)}
            className="w-full text-left px-3 py-2 rounded-lg transition-colors flex items-center gap-2"
            style={{
              backgroundColor: isActive ? 'var(--color-accent)' : 'transparent',
              color: isActive ? 'white' : 'var(--color-text)',
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.backgroundColor = 'transparent'
              }
            }}
          >
            <FileCode className="w-4 h-4 flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{fileName}</p>
              {dirPath && (
                <p
                  className="text-xs truncate"
                  style={{
                    color: isActive ? 'rgba(255,255,255,0.7)' : 'var(--color-textMuted)',
                  }}
                >
                  {dirPath}
                </p>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}

/**
 * EventCard renders a single event from the session replay timeline.
 *
 * @param {Object} props
 * @param {Object} props.event - Event object with t, type, data fields
 * @param {boolean} props.isActive - Whether this is the currently selected event
 * @param {function} props.onClick - Callback when the card is clicked
 */
function EventCard({ event, isActive, onClick }) {
  const config = EVENT_TYPE_CONFIG[event.type] || {
    label: event.type,
    icon: Clock,
    color: '#6b7280',
  }
  const Icon = config.icon
  const data = event.data || {}

  /** Generate a one-line summary for the event */
  const summary = useMemo(() => {
    if (event.type === 'tool_call') {
      return `${data.tool || 'Unknown'}: ${data.arguments?.file_path || data.result_preview || ''}`
    }
    if (event.type === 'file_write') {
      return data.file_path || 'File write'
    }
    if (event.type === 'bash') {
      return data.command || 'Bash command'
    }
    if (event.type === 'agent_call') {
      return data.agent || 'Sub-agent call'
    }
    return event.type
  }, [event, data])

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2.5 rounded-lg transition-all duration-150 flex items-start gap-2.5"
      style={{
        backgroundColor: isActive ? `${config.color}15` : 'transparent',
        borderLeft: isActive ? `3px solid ${config.color}` : '3px solid transparent',
      }}
      onMouseEnter={(e) => {
        if (!isActive) {
          e.currentTarget.style.backgroundColor = 'var(--color-bgTertiary)'
        }
      }}
      onMouseLeave={(e) => {
        if (!isActive) {
          e.currentTarget.style.backgroundColor = 'transparent'
        }
      }}
    >
      <div
        className="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center mt-0.5"
        style={{ backgroundColor: `${config.color}20`, color: config.color }}
      >
        <Icon className="w-3.5 h-3.5" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span
            className="text-xs font-medium"
            style={{ color: config.color }}
          >
            {config.label}
          </span>
          <span
            className="text-xs font-mono flex-shrink-0"
            style={{ color: 'var(--color-textMuted)' }}
          >
            {formatTime(event.t)}
          </span>
        </div>
        <p
          className="text-xs mt-0.5 truncate"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          {summary}
        </p>

        {/* Show result/output preview when active */}
        {isActive && (data.result_preview || data.output_preview) && (
          <div
            className="mt-2 p-2 rounded text-xs font-mono whitespace-pre-wrap break-all max-h-32 overflow-auto"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-textSecondary)',
            }}
          >
            {data.result_preview || data.output_preview}
          </div>
        )}
      </div>
    </button>
  )
}

/**
 * ReplayDetail page component providing the full session replay UI.
 *
 * Layout:
 * - Top: TimelineSlider with playback controls
 * - Left: File list panel (files affected by the session)
 * - Right: Event list / agent output panel
 * - Bottom: DiffViewer (when a file_write event is selected)
 */
function ReplayDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { session, loading, error } = useSessionDetail(id)

  const [currentTime, setCurrentTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackSpeed, setPlaybackSpeed] = useState(1)
  const [selectedEventIndex, setSelectedEventIndex] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)

  const playbackRef = useRef(null)

  /** Compute total session duration from events */
  const totalDuration = useMemo(() => {
    if (!session?.events?.length) return 0
    const lastEvent = session.events[session.events.length - 1]
    return (lastEvent?.t || 0) + 10
  }, [session])

  /** Convert events to TimelineSlider format (add id for keying) */
  const timelineEvents = useMemo(() => {
    if (!session?.events) return []
    return session.events.map((event, index) => ({
      ...event,
      id: index,
      timestamp: event.t,
    }))
  }, [session])

  /** Extract unique files from session events */
  const affectedFiles = useMemo(
    () => extractAffectedFiles(session?.events || []),
    [session],
  )

  /** Find the event closest to (but not exceeding) currentTime */
  const activeEventIndex = useMemo(() => {
    if (!session?.events?.length) return null
    let lastIndex = null
    for (let i = 0; i < session.events.length; i++) {
      if (session.events[i].t <= currentTime) {
        lastIndex = i
      }
    }
    return lastIndex
  }, [session, currentTime])

  /** The explicitly selected event (click) or the auto-tracked one (playback) */
  const displayedEventIndex = selectedEventIndex ?? activeEventIndex

  /** The currently displayed event object */
  const displayedEvent = useMemo(() => {
    if (displayedEventIndex == null || !session?.events) return null
    return session.events[displayedEventIndex]
  }, [displayedEventIndex, session])

  /** Diff data for the selected file_write event (if applicable) */
  const diffData = useMemo(() => {
    if (!displayedEvent || displayedEvent.type !== 'file_write') return null
    const data = displayedEvent.data || {}
    if (!data.old_content && !data.new_content) return null
    return {
      oldContent: data.old_content || '',
      newContent: data.new_content || '',
      filename: data.file_path || 'unknown',
    }
  }, [displayedEvent])

  /** Handle playback timer */
  useEffect(() => {
    if (isPlaying) {
      playbackRef.current = setInterval(() => {
        setCurrentTime((prev) => {
          const next = prev + (PLAYBACK_INTERVAL_MS / 1000) * playbackSpeed
          if (next >= totalDuration) {
            setIsPlaying(false)
            return totalDuration
          }
          return next
        })
      }, PLAYBACK_INTERVAL_MS)
    }

    return () => {
      if (playbackRef.current) {
        clearInterval(playbackRef.current)
        playbackRef.current = null
      }
    }
  }, [isPlaying, playbackSpeed, totalDuration])

  /** Handle seeking from the timeline slider */
  const handleTimeChange = useCallback((newTime) => {
    setCurrentTime(newTime)
    setSelectedEventIndex(null)
  }, [])

  /** Handle play/pause toggle */
  const handlePlayPauseToggle = useCallback(() => {
    setIsPlaying((prev) => {
      if (!prev && currentTime >= totalDuration) {
        setCurrentTime(0)
      }
      return !prev
    })
  }, [currentTime, totalDuration])

  /** Handle clicking an event marker on the timeline */
  const handleEventClick = useCallback((event) => {
    setSelectedEventIndex(event.id)
    setIsPlaying(false)
  }, [])

  /** Handle clicking an event card in the list */
  const handleEventCardClick = useCallback((index, event) => {
    setSelectedEventIndex(index)
    setCurrentTime(event.t)
    setIsPlaying(false)
  }, [])

  /** Handle file selection from file panel */
  const handleFileSelect = useCallback(
    (filePath) => {
      setSelectedFile(filePath)
      // Find the latest file_write event for this file
      if (session?.events) {
        for (let i = session.events.length - 1; i >= 0; i--) {
          const evt = session.events[i]
          if (evt.type === 'file_write' && evt.data?.file_path === filePath) {
            setSelectedEventIndex(i)
            setCurrentTime(evt.t)
            break
          }
        }
      }
    },
    [session],
  )

  /** Loading state */
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div
          className="flex items-center space-x-3"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          <RefreshCw className="w-6 h-6 animate-spin" />
          <span>Загрузка сессии...</span>
        </div>
      </div>
    )
  }

  /** Error state with no fallback data */
  if (error && !session) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/replay')}
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          <ArrowLeft className="w-4 h-4" />
          К списку сессий
        </button>
        <div
          className="rounded-lg p-6 border text-center"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171',
          }}
        >
          <XCircle className="w-10 h-10 mx-auto mb-3" />
          <p className="font-medium">Не удалось загрузить сессию</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
      </div>
    )
  }

  if (!session) return null

  const StatusIcon =
    session.status === 'completed'
      ? CheckCircle
      : session.status === 'failed'
        ? XCircle
        : session.status === 'running'
          ? Loader2
          : Clock

  const statusColor = STATUS_COLORS[session.status] || STATUS_COLORS.unknown

  return (
    <div className="space-y-4">
      {/* Header with back navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/replay')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-textSecondary)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--color-text)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--color-textSecondary)'
            }}
          >
            <ArrowLeft className="w-4 h-4" />
            Назад
          </button>

          <div className="flex items-center gap-3">
            <div
              className="flex items-center justify-center w-9 h-9 rounded-lg"
              style={{ backgroundColor: 'var(--color-bgTertiary)' }}
            >
              <Hash className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
            </div>
            <div>
              <h2
                className="text-lg font-bold"
                style={{ color: 'var(--color-text)' }}
              >
                Session #{session.session_id}
              </h2>
              <div className="flex items-center gap-2">
                {session.issue_id && (
                  <span
                    className="text-xs font-medium"
                    style={{ color: 'var(--color-textSecondary)' }}
                  >
                    {session.issue_id}
                  </span>
                )}
                <span
                  className="inline-flex items-center gap-1 text-xs font-medium capitalize"
                  style={{ color: statusColor }}
                >
                  <StatusIcon
                    className={`w-3 h-3 ${session.status === 'running' ? 'animate-spin' : ''}`}
                  />
                  {session.status}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error banner (when using fallback data) */}
      {error && (
        <div
          className="rounded-lg px-4 py-2 text-xs border"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'rgba(239, 68, 68, 0.2)',
            color: '#f87171',
          }}
        >
          Ошибка API: {error}. Показаны демо-данные.
        </div>
      )}

      {/* Timeline Slider */}
      <TimelineSlider
        events={timelineEvents}
        currentTime={currentTime}
        totalDuration={totalDuration}
        isPlaying={isPlaying}
        playbackSpeed={playbackSpeed}
        onTimeChange={handleTimeChange}
        onPlayPauseToggle={handlePlayPauseToggle}
        onSpeedChange={setPlaybackSpeed}
        onEventClick={handleEventClick}
      />

      {/* Main content: File list + Event output */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left panel: File list */}
        <div
          className="lg:col-span-3 rounded-xl p-4 border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-cardBorder)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <FileCode className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
            <h3
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text)' }}
            >
              Файлы
            </h3>
            <span
              className="text-xs px-1.5 py-0.5 rounded-full"
              style={{
                backgroundColor: 'var(--color-bgTertiary)',
                color: 'var(--color-textMuted)',
              }}
            >
              {affectedFiles.length}
            </span>
          </div>
          <div className="max-h-80 overflow-auto">
            <FileListPanel
              files={affectedFiles}
              selectedFile={selectedFile}
              onSelect={handleFileSelect}
            />
          </div>
        </div>

        {/* Right panel: Event list / Agent output */}
        <div
          className="lg:col-span-9 rounded-xl p-4 border"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            borderColor: 'var(--color-cardBorder)',
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
              <h3
                className="text-sm font-semibold"
                style={{ color: 'var(--color-text)' }}
              >
                Вывод агента
              </h3>
              <span
                className="text-xs px-1.5 py-0.5 rounded-full"
                style={{
                  backgroundColor: 'var(--color-bgTertiary)',
                  color: 'var(--color-textMuted)',
                }}
              >
                {session.events?.length || 0} событий
              </span>
            </div>

            {displayedEventIndex != null && (
              <span
                className="text-xs"
                style={{ color: 'var(--color-textMuted)' }}
              >
                Событие {displayedEventIndex + 1} из {session.events?.length || 0}
              </span>
            )}
          </div>

          <div className="max-h-96 overflow-auto space-y-0.5">
            {(session.events || []).map((event, index) => (
              <EventCard
                key={index}
                event={event}
                isActive={index === displayedEventIndex}
                onClick={() => handleEventCardClick(index, event)}
              />
            ))}

            {(!session.events || session.events.length === 0) && (
              <div
                className="flex items-center justify-center py-12"
                style={{ color: 'var(--color-textMuted)' }}
              >
                <span className="text-sm">Нет записанных событий</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Diff Viewer (shows when a file_write event is selected) */}
      {diffData && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <ChevronRight className="w-4 h-4" style={{ color: 'var(--color-accent)' }} />
            <h3
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text)' }}
            >
              Изменения файла
            </h3>
          </div>
          <DiffViewer
            oldContent={diffData.oldContent}
            newContent={diffData.newContent}
            filename={diffData.filename}
          />
        </div>
      )}
    </div>
  )
}

export default ReplayDetail
