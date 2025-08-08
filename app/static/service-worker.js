const CACHE_NAME = 'ambp-v2.0';
const STATIC_CACHE = 'ambp-static-v2.0';
const DYNAMIC_CACHE = 'ambp-dynamic-v2.0';

const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/img/logo.png',
  '/static/img/favicon-32x32.png',
  '/static/img/android-chrome-192x192.png',
  '/static/img/android-chrome-512x512.png',
  'https://cdn.tailwindcss.com',
  'https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js',
  'https://unpkg.com/htmx.org@1.9.2',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== STATIC_CACHE && cacheName !== DYNAMIC_CACHE) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        if (response) {
          return response;
        }
        
        return fetch(event.request)
          .then((fetchResponse) => {
            if (!fetchResponse || fetchResponse.status !== 200 || fetchResponse.type !== 'basic') {
              return fetchResponse;
            }
            
            const responseToCache = fetchResponse.clone();
            caches.open(DYNAMIC_CACHE)
              .then((cache) => {
                cache.put(event.request, responseToCache);
              });
            
            return fetchResponse;
          })
          .catch(() => {
            if (event.request.destination === 'document') {
              return caches.match('/');
            }
          });
      })
  );
});