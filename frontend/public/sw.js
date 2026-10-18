/* HealthLens Service Worker v1.0.0 */
const CACHE_NAME = 'healthlens-v1';
const APP_SHELL = [
  '/app/',
  '/app/index.html',
  '/app/icons/icon.svg',
  '/app/manifest.json',
];

// Strategy:
// - App shell: cache-first, update from network
// - Static assets (JS/CSS): stale-while-revalidate
// - API calls: network-first, fall back to cache
// - Navigation requests: network-first, fall back to offline page

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle requests from this origin
  if (url.origin !== self.location.origin) return;

  // API requests: network-first
  if (request.method === 'GET' && url.pathname.startsWith('/app/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Navigation requests: network-first, fall back to offline
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match('/app/offline.html'))
    );
    return;
  }

  // Static assets (JS, CSS, images): stale-while-revalidate
  if (
    request.method === 'GET' &&
    url.pathname.match(/\.(js|css|svg|png|jpg|jpeg|gif|webp|woff2?)$/)
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const fetchPromise = fetch(request)
          .then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            }
            return response;
          })
          .catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Everything else: network-first
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});

// Periodic background sync for health data
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
