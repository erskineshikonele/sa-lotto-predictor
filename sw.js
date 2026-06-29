// Service Worker for SA Lotto Predictor
const CACHE_NAME = 'sa-lotto-predictor-v1';
const urlsToCache = [
  '/sa-lotto-predictor/',
  '/sa-lotto-predictor/index.html',
  '/sa-lotto-predictor/manifest.json',
  '/sa-lotto-predictor/icons/icon-72x72.png',
  '/sa-lotto-predictor/icons/icon-96x96.png',
  '/sa-lotto-predictor/icons/icon-128x128.png',
  '/sa-lotto-predictor/icons/icon-144x144.png',
  '/sa-lotto-predictor/icons/icon-152x152.png',
  '/sa-lotto-predictor/icons/icon-192x192.png',
  '/sa-lotto-predictor/icons/icon-384x384.png',
  '/sa-lotto-predictor/icons/icon-512x512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js',
  'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js'
];

// Install event - cache core assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Cache hit - return response
        if (response) {
          return response;
        }
        return fetch(event.request).then(
          response => {
            // Check if we received a valid response
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }

            // Clone the response
            const responseToCache = response.clone();

            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });

            return response;
          }
        );
      })
  );
});

// Handle offline fallback
self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match('/sa-lotto-predictor/index.html');
      })
    );
  }
});

// Background sync for offline saves
self.addEventListener('sync', event => {
  if (event.tag === 'sync-picks') {
    event.waitUntil(syncPicks());
  }
});

async function syncPicks() {
  // Implement pick syncing logic here
  const cache = await caches.open('pending-picks');
  const requests = await cache.keys();
  
  for (const request of requests) {
    try {
      const response = await fetch(request);
      if (response.ok) {
        await cache.delete(request);
      }
    } catch (error) {
      console.error('Sync failed:', error);
    }
  }
}

// Push notifications
self.addEventListener('push', event => {
  const options = {
    body: event.data.text(),
    icon: '/sa-lotto-predictor/icons/icon-192x192.png',
    badge: '/sa-lotto-predictor/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'generate',
        title: 'Generate Picks'
      },
      {
        action: 'close',
        title: 'Close'
      }
    ]
  };

  event.waitUntil(
    self.registration.showNotification('SA Lotto Predictor', options)
  );
});

// Notification click
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'generate') {
    event.waitUntil(
      clients.openWindow('/sa-lotto-predictor/?action=generate')
    );
  } else {
    event.waitUntil(
      clients.openWindow('/sa-lotto-predictor/')
    );
  }
});