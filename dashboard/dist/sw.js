// Service Worker for Agent Analytics Dashboard PWA
const CACHE_NAME = 'agent-dashboard-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/vite.svg'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Caching static assets');
      return cache.addAll(STATIC_ASSETS);
    })
  );
  // Activate immediately
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  // Take control of all pages immediately
  self.clients.claim();
});

// Fetch event - network first, fallback to cache
self.addEventListener('fetch', (event) => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // Skip API requests - always go to network
  if (event.request.url.includes('/api/')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Clone response before caching
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseClone);
        });
        return response;
      })
      .catch(() => {
        // Network failed, try cache
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // Return offline page for navigation requests
          if (event.request.mode === 'navigate') {
            return caches.match('/');
          }
          return new Response('Offline', { status: 503 });
        });
      })
  );
});

// Push notification event
self.addEventListener('push', (event) => {
  console.log('[SW] Push received');

  let data = {
    title: 'Agent Dashboard',
    body: 'You have a new notification',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-72x72.png',
    tag: 'default',
    data: {}
  };

  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/icons/icon-192x192.png',
    badge: data.badge || '/icons/icon-72x72.png',
    vibrate: [100, 50, 100],
    tag: data.tag,
    data: data.data,
    actions: data.actions || [
      { action: 'view', title: 'View' },
      { action: 'dismiss', title: 'Dismiss' }
    ],
    requireInteraction: data.requireInteraction || false
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification click');
  event.notification.close();

  const action = event.action;
  const notificationData = event.notification.data || {};

  if (action === 'dismiss') {
    return;
  }

  // Default action or 'view' - open the app
  const urlToOpen = notificationData.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // Check if app is already open
      for (const client of windowClients) {
        if (client.url === urlToOpen && 'focus' in client) {
          return client.focus();
        }
      }
      // Open new window
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});

// Background sync for queued actions
self.addEventListener('sync', (event) => {
  console.log('[SW] Sync event:', event.tag);

  if (event.tag === 'queue-actions') {
    event.waitUntil(processQueuedActions());
  }
});

// Process queued actions when back online
async function processQueuedActions() {
  try {
    // Get queued actions from IndexedDB
    const db = await openDB();
    const tx = db.transaction('queuedActions', 'readwrite');
    const store = tx.objectStore('queuedActions');
    const actions = await store.getAll();

    for (const action of actions) {
      try {
        const response = await fetch(action.url, {
          method: action.method,
          headers: action.headers,
          body: action.body
        });

        if (response.ok) {
          // Remove from queue
          await store.delete(action.id);
          console.log('[SW] Processed queued action:', action.id);
        }
      } catch (error) {
        console.error('[SW] Failed to process action:', action.id, error);
      }
    }
  } catch (error) {
    console.error('[SW] Failed to process queue:', error);
  }
}

// Simple IndexedDB helper
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('AgentDashboard', 1);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('queuedActions')) {
        db.createObjectStore('queuedActions', { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('offlineState')) {
        db.createObjectStore('offlineState', { keyPath: 'key' });
      }
    };
  });
}

// Periodic background sync for status updates
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'check-status') {
    event.waitUntil(checkAgentStatus());
  }
});

async function checkAgentStatus() {
  try {
    const response = await fetch('/api/agent/status');
    if (response.ok) {
      const status = await response.json();

      // Notify if there are important updates
      if (status.needsAttention) {
        self.registration.showNotification('Agent Status', {
          body: status.message,
          icon: '/icons/icon-192x192.png',
          tag: 'status-update'
        });
      }
    }
  } catch (error) {
    console.log('[SW] Status check failed (offline)');
  }
}
