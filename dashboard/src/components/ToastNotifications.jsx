import React, { useState, useEffect, useCallback } from 'react'
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Info,
  X,
  Bell,
  Play,
  Pause,
  TestTube,
} from 'lucide-react'

/**
 * Toast notification types and their configurations
 */
const TOAST_TYPES = {
  success: {
    icon: CheckCircle,
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.1)',
    borderColor: 'rgba(34, 197, 94, 0.2)',
  },
  error: {
    icon: XCircle,
    color: '#ef4444',
    bgColor: 'rgba(239, 68, 68, 0.1)',
    borderColor: 'rgba(239, 68, 68, 0.2)',
  },
  warning: {
    icon: AlertTriangle,
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.1)',
    borderColor: 'rgba(245, 158, 11, 0.2)',
  },
  info: {
    icon: Info,
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.1)',
    borderColor: 'rgba(59, 130, 246, 0.2)',
  },
  session_start: {
    icon: Play,
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.1)',
    borderColor: 'rgba(34, 197, 94, 0.2)',
  },
  session_end: {
    icon: Pause,
    color: '#6b7280',
    bgColor: 'rgba(107, 114, 128, 0.1)',
    borderColor: 'rgba(107, 114, 128, 0.2)',
  },
  test_failed: {
    icon: TestTube,
    color: '#ef4444',
    bgColor: 'rgba(239, 68, 68, 0.1)',
    borderColor: 'rgba(239, 68, 68, 0.2)',
  },
  task_complete: {
    icon: CheckCircle,
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.1)',
    borderColor: 'rgba(34, 197, 94, 0.2)',
  },
}

/**
 * Single Toast component
 */
function Toast({ toast, onDismiss }) {
  const [isExiting, setIsExiting] = useState(false)

  const config = TOAST_TYPES[toast.type] || TOAST_TYPES.info
  const Icon = config.icon

  useEffect(() => {
    if (toast.duration !== 0) {
      const timer = setTimeout(() => {
        handleDismiss()
      }, toast.duration || 5000)

      return () => clearTimeout(timer)
    }
  }, [toast.duration])

  const handleDismiss = () => {
    setIsExiting(true)
    setTimeout(() => {
      onDismiss(toast.id)
    }, 200) // Animation duration
  }

  return (
    <div
      className={`
        flex items-start gap-3 p-4 rounded-lg border shadow-lg
        transition-all duration-200 ease-out
        ${isExiting ? 'opacity-0 translate-x-full' : 'opacity-100 translate-x-0'}
      `}
      style={{
        backgroundColor: config.bgColor,
        borderColor: config.borderColor,
        maxWidth: '400px',
      }}
      role="alert"
    >
      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5">
        <Icon className="w-5 h-5" style={{ color: config.color }} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {toast.title && (
          <p
            className="text-sm font-semibold"
            style={{ color: 'var(--color-text)' }}
          >
            {toast.title}
          </p>
        )}
        {toast.message && (
          <p
            className={`text-sm ${toast.title ? 'mt-1' : ''}`}
            style={{ color: 'var(--color-textSecondary)' }}
          >
            {toast.message}
          </p>
        )}

        {/* Action button */}
        {toast.action && (
          <button
            onClick={() => {
              toast.action.onClick?.()
              handleDismiss()
            }}
            className="mt-2 text-sm font-medium transition-colors"
            style={{ color: config.color }}
          >
            {toast.action.label}
          </button>
        )}
      </div>

      {/* Dismiss button */}
      {toast.dismissible !== false && (
        <button
          onClick={handleDismiss}
          className="flex-shrink-0 p-1 rounded-full transition-colors"
          style={{ color: 'var(--color-textMuted)' }}
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}

/**
 * Toast Container component - manages toast stack
 */
function ToastContainer({ toasts = [], onDismiss, position = 'top-right', maxToasts = 5 }) {
  const positionStyles = {
    'top-right': 'top-4 right-4',
    'top-left': 'top-4 left-4',
    'bottom-right': 'bottom-4 right-4',
    'bottom-left': 'bottom-4 left-4',
    'top-center': 'top-4 left-1/2 -translate-x-1/2',
    'bottom-center': 'bottom-4 left-1/2 -translate-x-1/2',
  }

  // Limit visible toasts
  const visibleToasts = toasts.slice(0, maxToasts)

  return (
    <div
      className={`fixed z-50 flex flex-col gap-2 ${positionStyles[position] || positionStyles['top-right']}`}
      style={{ pointerEvents: 'none' }}
    >
      {visibleToasts.map(toast => (
        <div key={toast.id} style={{ pointerEvents: 'auto' }}>
          <Toast toast={toast} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  )
}

/**
 * Hook for managing toast notifications
 */
export function useToasts() {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((toast) => {
    const id = toast.id || `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    setToasts(prev => [{ ...toast, id }, ...prev])
    return id
  }, [])

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const dismissAll = useCallback(() => {
    setToasts([])
  }, [])

  // Convenience methods
  const showSuccess = useCallback((message, options = {}) => {
    return addToast({ type: 'success', message, ...options })
  }, [addToast])

  const showError = useCallback((message, options = {}) => {
    return addToast({ type: 'error', message, ...options })
  }, [addToast])

  const showWarning = useCallback((message, options = {}) => {
    return addToast({ type: 'warning', message, ...options })
  }, [addToast])

  const showInfo = useCallback((message, options = {}) => {
    return addToast({ type: 'info', message, ...options })
  }, [addToast])

  return {
    toasts,
    addToast,
    dismissToast,
    dismissAll,
    showSuccess,
    showError,
    showWarning,
    showInfo,
  }
}

/**
 * Provider component for toast context
 */
export function ToastProvider({ children, position = 'top-right', maxToasts = 5 }) {
  const { toasts, dismissToast, ...methods } = useToasts()

  return (
    <>
      {children}
      <ToastContainer
        toasts={toasts}
        onDismiss={dismissToast}
        position={position}
        maxToasts={maxToasts}
      />
    </>
  )
}

export { ToastContainer, Toast }
export default ToastContainer
