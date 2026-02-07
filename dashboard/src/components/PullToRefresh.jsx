import React, { useState, useRef, useCallback } from 'react'
import { RefreshCw } from 'lucide-react'

const PULL_THRESHOLD = 60
const MAX_PULL = 100

function PullToRefresh({ children, onRefresh, disabled = false }) {
  const [pullDistance, setPullDistance] = useState(0)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isPulling, setIsPulling] = useState(false)
  const startY = useRef(0)
  const containerRef = useRef(null)

  const handleTouchStart = useCallback((e) => {
    if (disabled || isRefreshing) return

    // Only start pull if at top of scroll
    if (containerRef.current && containerRef.current.scrollTop === 0) {
      startY.current = e.touches[0].clientY
      setIsPulling(true)
    }
  }, [disabled, isRefreshing])

  const handleTouchMove = useCallback((e) => {
    if (!isPulling || disabled || isRefreshing) return

    const currentY = e.touches[0].clientY
    const diff = currentY - startY.current

    if (diff > 0) {
      // Apply resistance as pull increases
      const resistance = 0.5
      const pull = Math.min(diff * resistance, MAX_PULL)
      setPullDistance(pull)

      // Prevent default scrolling while pulling
      if (containerRef.current && containerRef.current.scrollTop === 0) {
        e.preventDefault()
      }
    }
  }, [isPulling, disabled, isRefreshing])

  const handleTouchEnd = useCallback(async () => {
    if (!isPulling || disabled) return

    setIsPulling(false)

    if (pullDistance >= PULL_THRESHOLD && onRefresh) {
      setIsRefreshing(true)
      setPullDistance(PULL_THRESHOLD)

      try {
        await onRefresh()
      } catch (error) {
        console.error('Refresh failed:', error)
      }

      // Animate back
      setIsRefreshing(false)
      setPullDistance(0)
    } else {
      // Spring back
      setPullDistance(0)
    }
  }, [isPulling, pullDistance, onRefresh, disabled])

  const progress = Math.min(pullDistance / PULL_THRESHOLD, 1)
  const rotation = progress * 360

  return (
    <div
      ref={containerRef}
      className="pull-to-refresh-container relative overflow-auto h-full"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
    >
      {/* Pull indicator */}
      <div
        className="absolute left-1/2 -translate-x-1/2 z-10 flex items-center justify-center transition-transform"
        style={{
          top: -48,
          transform: `translateX(-50%) translateY(${pullDistance}px)`,
          opacity: pullDistance > 10 ? 1 : 0,
          transition: isPulling ? 'none' : 'transform 0.3s ease, opacity 0.3s ease'
        }}
      >
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center"
          style={{
            backgroundColor: 'var(--color-cardBg)',
            border: '1px solid var(--color-border)'
          }}
        >
          <RefreshCw
            className="w-5 h-5"
            style={{
              color: progress >= 1 ? 'var(--color-accent)' : 'var(--color-textMuted)',
              transform: `rotate(${rotation}deg)`,
              transition: isPulling ? 'none' : 'transform 0.3s ease'
            }}
          />
        </div>
      </div>

      {/* Content with pull offset */}
      <div
        style={{
          transform: `translateY(${pullDistance}px)`,
          transition: isPulling ? 'none' : 'transform 0.3s ease'
        }}
      >
        {children}
      </div>

      {/* Refreshing overlay */}
      {isRefreshing && (
        <div
          className="absolute inset-0 flex items-start justify-center pt-4 z-20"
          style={{ backgroundColor: 'rgba(0, 0, 0, 0.1)' }}
        >
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center"
            style={{
              backgroundColor: 'var(--color-cardBg)',
              border: '1px solid var(--color-border)'
            }}
          >
            <RefreshCw
              className="w-5 h-5 animate-spin"
              style={{ color: 'var(--color-accent)' }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default PullToRefresh
