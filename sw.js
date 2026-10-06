/* Brighton Weekend service worker.
 * Caching only. Earlier versions rewrote index.html here to inject the Search
 * tab and day filters; those features now live in index.html.
 *
 * Strategy:
 *  - Pages, CSS, JS and data files: network first, fall back to cache offline.
 *  - Images and icons: cache first (they are versioned by filename or ?v=).
 * Bump VERSION whenever you want every installed copy to drop old caches.
 */
const VERSION = 'bw-v59';
const CORE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './favicon.ico',
  './vendor/supabase-js-2.117.2.js',
  './icons/icon-32.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-192-maskable.png',
  './icons/icon-512-maskable.png',
  './icons/apple-touch-icon.png',
  './about.html',
  './privacy.html',
  './terms.html'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(VERSION)
      .then(cache => Promise.all(CORE.map(url => cache.add(url).catch(err => console.warn('Precache skipped', url, err)))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Network-first responses are stored under the address WITHOUT its query string.
// The app fetches events.json?refresh=<timestamp> on every load; keying the cache
// by the full address stored a new ~400 KB copy each time and never removed them.
function cacheKey(request) {
  const url = new URL(request.url);
  url.search = '';
  return url.href;
}

function networkFirst(request) {
  const key = cacheKey(request);
  return fetch(request, {cache: 'no-store'})
    .then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(VERSION).then(cache => cache.put(key, copy));
      }
      return response;
    })
    .catch(() => caches.match(key)
      .then(hit => hit || caches.match(request, {ignoreSearch: true}))
      .then(hit => hit || (request.mode === 'navigate' ? caches.match('./index.html') : undefined))
      .then(hit => hit || Response.error()));
}

function cacheFirst(request) {
  return caches.match(request).then(hit => hit || fetch(request).then(response => {
    if (response.ok) {
      const copy = response.clone();
      caches.open(VERSION).then(cache => cache.put(request, copy));
    }
    return response;
  }));
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // Supabase, fonts: straight to network
  const isFresh = request.mode === 'navigate' || /\.(html|css|js|json|webmanifest)$/.test(url.pathname) || url.pathname.endsWith('/');
  event.respondWith(isFresh ? networkFirst(request) : cacheFirst(request));
});
