import React, { useRef, useCallback, useMemo } from 'react'
import { Play, Pause, SkipForward, Clock } from 'lucide-react'

/** Available playback speed options */
const SPEED_OPTIONS = [1, 2, 4]

/** Minimum pixel distance to distinguish separate event markers */
const MIN_MARKER_GAP_PX = 4

/**
 * Format a duration in seconds to MM:SS or HH:MM:SS if over one hour.
 *
 * @param {number} totalSeconds - Duration in seconds
 * @returns {string} Formatted time string
 */
function formatTime(totalSeconds) {
  const absSeconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(absSeconds / 3600)
  const minutes = Math.floor((absSeconds % 3600) / 60)
  const seconds = absSeconds % 60

  const pad = (n) => String(n).padStart(2, '0')

  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
  }
  return `${pad(minutes)}:${pad(seconds)}`
}

/**
 * Compute the percentage position of a timestamp within the session duration.
 *
 * @param {number} timestampSeconds - Event timestamp in seconds from session start
 * @param {number} totalDuration - Total session duration in seconds
 * @returns {number} Percentage (0-100)
 */
function toPercent(timestampSeconds, totalDuration) {
  if (totalDuration <= 0) return 0
  return Math.min(100, Math.max(0, (timestampSeconds / totalDuration) * 100))
}

/**
 * Timeline Slider component for session replay playback.
 * Displays a scrubable timeline with event markers and playback controls.
 *
 * @param {Object} props
 * @param {Array} props.events - Array of event objects with `timestamp` (seconds from start) and optional `type`
 * @param {number} props.currentTime - Current playback position in seconds
 * @param {number} props.totalDuration - Total session duration in seconds
 * @param {boolean} props.isPlaying - Whether playback is currently active
 * @param {number} props.playbackSpeed - Current playback speed (1, 2, or 4)
 * @param {function} props.onTimeChange - Called with new time (seconds) when user seeks
 * @param {function} props.onPlayPauseToggle - Called when play/pause is toggled
 * @param {function} props.onSpeedChange - Called with new speed value
 * @param {function} props.onEventClick - Called with the event object when an event marker is clicked
 */
function TimelineSlider({
  events = [],
  currentTime = 0,
  totalDuration = 0,
  isPlaying = false,
  playbackSpeed = 1,
  onTimeChange,
  onPlayPauseToggle,
  onSpeedChange,
  onEventClick,
}) {
  const trackRef = useRef(null)

  /** Sorted events with pre-computed percentage positions */
  const sortedEvents = useMemo(() => {
    return [...events]
      .sort((a, b) => a.timestamp - b.timestamp)
      .map((event) => ({
        ...event,
        percent: toPercent(event.timestamp, totalDuration),
      }))
  }, [events, totalDuration])

  /** Current playback position as a percentage */
  const progressPercent = useMemo(
    () => toPercent(currentTime, totalDuration),
    [currentTime, totalDuration],
  )

  /**
   * Convert a mouse/pointer clientX position to a time value
   * based on the track element bounds.
   */
  const clientXToTime = useCallback(
    (clientX) => {
      const track = trackRef.current
      if (!track || totalDuration <= 0) return 0

      const rect = track.getBoundingClientRect()
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
      return ratio * totalDuration
    },
    [totalDuration],
  )

  /** Handle click on the track to seek */
  const handleTrackClick = useCallback(
    (e) => {
      const newTime = clientXToTime(e.clientX)
      onTimeChange?.(newTime)
    },
    [clientXToTime, onTimeChange],
  )

  /** Cycle to the next playback speed */
  const handleSpeedCycle = useCallback(() => {
    const currentIndex = SPEED_OPTIONS.indexOf(playbackSpeed)
    const nextIndex = (currentIndex + 1) % SPEED_OPTIONS.length
    onSpeedChange?.(SPEED_OPTIONS[nextIndex])
  }, [playbackSpeed, onSpeedChange])

  /** Jump to the next event after currentTime */
  const handleSkipToNext = useCallback(() => {
    const nextEvent = sortedEvents.find((e) => e.timestamp > currentTime)
    if (nextEvent) {
      onTimeChange?.(nextEvent.timestamp)
    }
  }, [sortedEvents, currentTime, onTimeChange])

  /** Handle clicking on an individual event marker */
  const handleMarkerClick = useCallback(
    (event, e) => {
      e.stopPropagation()
      onTimeChange?.(event.timestamp)
      onEventClick?.(event)
    },
    [onTimeChange, onEventClick],
  )

  /**
   * Determine whether a marker should be visually distinct or merged
   * with its neighbors (based on pixel distance).
   */
  const visibleMarkers = useMemo(() => {
    const track = trackRef.current
    const trackWidth = track ? track.getBoundingClientRect().width : 800

    const markers = []
    let lastPixel = -Infinity

    for (const event of sortedEvents) {
      const pixel = (event.percent / 100) * trackWidth
      if (pixel - lastPixel >= MIN_MARKER_GAP_PX) {
        markers.push({ ...event, merged: false })
        lastPixel = pixel
      } else {
        markers.push({ ...event, merged: true })
      }
    }
    return markers
  }, [sortedEvents])

  const hasEvents = sortedEvents.length > 0

  return (
    <div
      className="rounded-xl p-4 md:p-6 border"
      style={{
        backgroundColor: 'var(--color-cardBg)',
        borderColor: 'var(--color-cardBorder)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <Clock className="w-5 h-5" style={{ color: 'var(--color-accent)' }} />
          <h3
            className="font-semibold text-sm"
            style={{ color: 'var(--color-text)' }}
          >
            Session Replay
          </h3>
          {hasEvents && (
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: 'var(--color-bgTertiary)',
                color: 'var(--color-textSecondary)',
              }}
            >
              {sortedEvents.length} events
            </span>
          )}
        </div>

        {/* Time Display */}
        <div
          className="text-sm font-mono"
          style={{ color: 'var(--color-textSecondary)' }}
        >
          <span style={{ color: 'var(--color-text)' }}>
            {formatTime(currentTime)}
          </span>
          {' / '}
          {formatTime(totalDuration)}
        </div>
      </div>

      {/* Timeline Track */}
      <div className="mb-4">
        <div
          ref={trackRef}
          className="relative h-8 rounded-lg cursor-pointer group"
          style={{ backgroundColor: 'var(--color-bgTertiary)' }}
          onClick={handleTrackClick}
          role="slider"
          aria-label="Playback timeline"
          aria-valuenow={Math.round(currentTime)}
          aria-valuemin={0}
          aria-valuemax={Math.round(totalDuration)}
          tabIndex={0}
        >
          {/* Progress fill */}
          <div
            className="absolute top-0 left-0 h-full rounded-lg transition-[width] duration-100"
            style={{
              width: `${progressPercent}%`,
              backgroundColor: 'var(--color-accent)',
              opacity: 0.25,
            }}
          />

          {/* Event markers */}
          {visibleMarkers.map((event, index) => (
            <button
              key={event.id || index}
              className={`absolute top-1/2 -translate-y-1/2 rounded-full transition-transform
                hover:scale-150 focus:scale-150 focus:outline-none focus:ring-2 focus:ring-offset-1
                ${event.merged ? 'w-1.5 h-1.5' : 'w-2.5 h-2.5'}`}
              style={{
                left: `${event.percent}%`,
                backgroundColor: event.timestamp <= currentTime
                  ? 'var(--color-accent)'
                  : 'var(--color-textMuted)',
                transform: `translateX(-50%) translateY(-50%)`,
                ringColor: 'var(--color-accent)',
              }}
              onClick={(e) => handleMarkerClick(event, e)}
              title={`${event.type || 'Event'} at ${formatTime(event.timestamp)}`}
              aria-label={`Jump to ${event.type || 'event'} at ${formatTime(event.timestamp)}`}
            />
          ))}

          {/* Playhead indicator */}
          <div
            className="absolute top-0 h-full w-0.5 transition-[left] duration-100"
            style={{
              left: `${progressPercent}%`,
              backgroundColor: 'var(--color-accent)',
            }}
          >
            <div
              className="absolute -top-1 left-1/2 -translate-x-1/2 w-3 h-3 rounded-full shadow-md"
              style={{ backgroundColor: 'var(--color-accent)' }}
            />
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          {/* Play / Pause */}
          <button
            onClick={onPlayPauseToggle}
            className="p-2 rounded-lg transition-colors hover:opacity-80"
            style={{
              backgroundColor: 'var(--color-accent)',
              color: 'white',
            }}
            aria-label={isPlaying ? 'Pause playback' : 'Start playback'}
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </button>

          {/* Skip to next event */}
          <button
            onClick={handleSkipToNext}
            disabled={!hasEvents}
            className="p-2 rounded-lg transition-colors disabled:opacity-40"
            style={{
              backgroundColor: 'var(--color-bgTertiary)',
              color: 'var(--color-textSecondary)',
            }}
            aria-label="Skip to next event"
            title="Next event"
          >
            <SkipForward className="w-4 h-4" />
          </button>
        </div>

        {/* Speed Control */}
        <div className="flex items-center space-x-1">
          {SPEED_OPTIONS.map((speed) => (
            <button
              key={speed}
              onClick={() => onSpeedChange?.(speed)}
              className="px-2.5 py-1 text-xs font-medium rounded-md transition-colors"
              style={{
                backgroundColor:
                  playbackSpeed === speed
                    ? 'var(--color-accent)'
                    : 'var(--color-bgTertiary)',
                color:
                  playbackSpeed === speed
                    ? 'white'
                    : 'var(--color-textSecondary)',
              }}
              aria-label={`Set playback speed to ${speed}x`}
            >
              {speed}x
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default TimelineSlider
