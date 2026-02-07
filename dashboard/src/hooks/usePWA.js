import { useState, useEffect, useCallback } from 'react'

export function usePWA() {
  const [isInstalled, setIsInstalled] = useState(false)
  const [canInstall, setCanInstall] = useState(false)
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [pushSubscription, setPushSubscription] = useState(null)
  const [notificationPermission, setNotificationPermission] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'default'
  )

  // Track install prompt
  useEffect(() => {
    const handleBeforeInstall = (e) => {
      e.preventDefault()
      window.deferredPrompt = e
      setCanInstall(true)
    }

    const handleAppInstalled = () => {
      window.deferredPrompt = null
      setCanInstall(false)
      setIsInstalled(true)
    }

    window.addEventListener('beforeinstallprompt', handleBeforeInstall)
    window.addEventListener('appinstalled', handleAppInstalled)

    // Check if already installed (standalone mode)
    if (window.matchMedia('(display-mode: standalone)').matches) {
      setIsInstalled(true)
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall)
      window.removeEventListener('appinstalled', handleAppInstalled)
    }
  }, [])

  // Track online status
  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  // Install PWA
  const install = useCallback(async () => {
    if (!window.deferredPrompt) return false

    try {
      window.deferredPrompt.prompt()
      const { outcome } = await window.deferredPrompt.userChoice

      if (outcome === 'accepted') {
        window.deferredPrompt = null
        setCanInstall(false)
        return true
      }
    } catch (error) {
      console.error('Install failed:', error)
    }

    return false
  }, [])

  // Request notification permission
  const requestNotifications = useCallback(async () => {
    if (typeof Notification === 'undefined') {
      return 'unsupported'
    }

    try {
      const permission = await Notification.requestPermission()
      setNotificationPermission(permission)
      return permission
    } catch (error) {
      console.error('Notification request failed:', error)
      return 'denied'
    }
  }, [])

  // Subscribe to push notifications
  const subscribeToPush = useCallback(async () => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      return null
    }

    try {
      const registration = await navigator.serviceWorker.ready

      // Get existing subscription or create new one
      let subscription = await registration.pushManager.getSubscription()

      if (!subscription) {
        // Replace with your VAPID public key
        const vapidPublicKey = 'YOUR_VAPID_PUBLIC_KEY'
        const convertedKey = urlBase64ToUint8Array(vapidPublicKey)

        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: convertedKey
        })
      }

      setPushSubscription(subscription)
      return subscription
    } catch (error) {
      console.error('Push subscription failed:', error)
      return null
    }
  }, [])

  // Unsubscribe from push notifications
  const unsubscribeFromPush = useCallback(async () => {
    if (pushSubscription) {
      try {
        await pushSubscription.unsubscribe()
        setPushSubscription(null)
        return true
      } catch (error) {
        console.error('Unsubscribe failed:', error)
      }
    }
    return false
  }, [pushSubscription])

  // Queue action for background sync
  const queueAction = useCallback(async (action) => {
    if (!('serviceWorker' in navigator)) return false

    try {
      // Store action in IndexedDB
      const db = await openDB()
      const tx = db.transaction('queuedActions', 'readwrite')
      const store = tx.objectStore('queuedActions')
      await store.add({
        ...action,
        timestamp: Date.now()
      })

      // Request background sync
      const registration = await navigator.serviceWorker.ready
      if ('sync' in registration) {
        await registration.sync.register('queue-actions')
      }

      return true
    } catch (error) {
      console.error('Queue action failed:', error)
      return false
    }
  }, [])

  return {
    isInstalled,
    canInstall,
    isOnline,
    notificationPermission,
    pushSubscription,
    install,
    requestNotifications,
    subscribeToPush,
    unsubscribeFromPush,
    queueAction
  }
}

// Helper function to convert VAPID key
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4)
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/')

  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

// Simple IndexedDB helper
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('AgentDashboard', 1)

    request.onerror = () => reject(request.error)
    request.onsuccess = () => resolve(request.result)

    request.onupgradeneeded = (event) => {
      const db = event.target.result
      if (!db.objectStoreNames.contains('queuedActions')) {
        db.createObjectStore('queuedActions', { keyPath: 'id', autoIncrement: true })
      }
      if (!db.objectStoreNames.contains('offlineState')) {
        db.createObjectStore('offlineState', { keyPath: 'key' })
      }
    }
  })
}

export default usePWA
