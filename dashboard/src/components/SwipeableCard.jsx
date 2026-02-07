import React, { useState, useRef, useCallback } from 'react'

const SWIPE_THRESHOLD = 80
const VELOCITY_THRESHOLD = 0.5

function SwipeableCard({
  children,
  onSwipeLeft,
  onSwipeRight,
  leftLabel = 'Next',
  rightLabel = 'Cancel',
  leftColor = 'rgba(34, 197, 94, 0.9)',
  rightColor = 'rgba(239, 68, 68, 0.9)',
  disabled = false
}) {
  const [translateX, setTranslateX] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef(0)
  const startTime = useRef(0)
  const cardRef = useRef(null)

  const handleTouchStart = useCallback((e) => {
    if (disabled) return
    startX.current = e.touches[0].clientX
    startTime.current = Date.now()
    setIsDragging(true)
  }, [disabled])

  const handleTouchMove = useCallback((e) => {
    if (!isDragging || disabled) return

    const currentX = e.touches[0].clientX
    const diff = currentX - startX.current

    // Limit the swipe distance with resistance
    const maxSwipe = 150
    const resistance = 0.5
    let newTranslateX = diff

    if (Math.abs(diff) > maxSwipe) {
      newTranslateX = diff > 0
        ? maxSwipe + (diff - maxSwipe) * resistance
        : -maxSwipe + (diff + maxSwipe) * resistance
    }

    setTranslateX(newTranslateX)
  }, [isDragging, disabled])

  const handleTouchEnd = useCallback(() => {
    if (!isDragging || disabled) return

    const endTime = Date.now()
    const duration = endTime - startTime.current
    const velocity = Math.abs(translateX) / duration

    // Check if swipe meets threshold
    if (Math.abs(translateX) > SWIPE_THRESHOLD || velocity > VELOCITY_THRESHOLD) {
      if (translateX > 0 && onSwipeRight) {
        // Animate out to the right
        setTranslateX(window.innerWidth)
        setTimeout(() => {
          onSwipeRight()
          setTranslateX(0)
        }, 200)
      } else if (translateX < 0 && onSwipeLeft) {
        // Animate out to the left
        setTranslateX(-window.innerWidth)
        setTimeout(() => {
          onSwipeLeft()
          setTranslateX(0)
        }, 200)
      } else {
        setTranslateX(0)
      }
    } else {
      // Spring back
      setTranslateX(0)
    }

    setIsDragging(false)
  }, [isDragging, translateX, onSwipeLeft, onSwipeRight, disabled])

  const showLeftIndicator = translateX < -30
  const showRightIndicator = translateX > 30

  return (
    <div className="swipe-container relative overflow-hidden">
      {/* Background indicators */}
      {showLeftIndicator && (
        <div
          className="swipe-indicator left visible"
          style={{ backgroundColor: leftColor }}
        >
          {leftLabel}
        </div>
      )}
      {showRightIndicator && (
        <div
          className="swipe-indicator right visible"
          style={{ backgroundColor: rightColor }}
        >
          {rightLabel}
        </div>
      )}

      {/* Card content */}
      <div
        ref={cardRef}
        className="swipeable-card"
        style={{
          transform: `translateX(${translateX}px)`,
          transition: isDragging ? 'none' : 'transform 0.2s ease-out',
          backgroundColor: showLeftIndicator
            ? 'var(--color-cardBg)'
            : showRightIndicator
              ? 'var(--color-cardBg)'
              : undefined
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onTouchCancel={handleTouchEnd}
      >
        {children}
      </div>
    </div>
  )
}

export default SwipeableCard
