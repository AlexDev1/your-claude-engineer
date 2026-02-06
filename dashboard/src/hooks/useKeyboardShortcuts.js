import { useEffect, useCallback } from 'react'

/**
 * Hook for managing keyboard shortcuts
 * @param {Object} shortcuts - Map of key combinations to handlers
 * @param {Object} options - Configuration options
 */
export function useKeyboardShortcuts(shortcuts, options = {}) {
  const {
    enabled = true,
    preventDefault = true,
    ignoreInputs = true,
  } = options

  const handleKeyDown = useCallback((event) => {
    if (!enabled) return

    // Ignore if typing in an input, textarea, or contenteditable
    if (ignoreInputs) {
      const target = event.target
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        // Allow Escape key in inputs
        if (event.key !== 'Escape') {
          return
        }
      }
    }

    // Build the key combination string
    const parts = []
    if (event.ctrlKey || event.metaKey) parts.push('Ctrl')
    if (event.shiftKey) parts.push('Shift')
    if (event.altKey) parts.push('Alt')

    // Normalize key names
    let key = event.key
    if (key === ' ') key = 'Space'
    if (key.length === 1) key = key.toUpperCase()

    parts.push(key)
    const combo = parts.join('+')

    // Also try just the key for simple shortcuts
    const simpleKey = key

    // Find matching handler
    const handler = shortcuts[combo] || shortcuts[simpleKey]

    if (handler) {
      if (preventDefault) {
        event.preventDefault()
      }
      handler(event)
    }
  }, [shortcuts, enabled, preventDefault, ignoreInputs])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}

/**
 * Common shortcuts configuration
 */
export const SHORTCUTS = {
  EDIT: 'E',
  COMMENT: 'C',
  PRIORITY_URGENT: '1',
  PRIORITY_HIGH: '2',
  PRIORITY_MEDIUM: '3',
  PRIORITY_LOW: '4',
  SAVE: 'Enter',
  CANCEL: 'Escape',
  NEW_ISSUE: 'N',
  UNDO: 'Ctrl+Z',
  SELECT_ALL: 'Ctrl+A',
  DELETE: 'Delete',
  NAVIGATE_UP: 'ArrowUp',
  NAVIGATE_DOWN: 'ArrowDown',
}

export default useKeyboardShortcuts
