/* Brighton Weekend service worker: caching only, it never changes a page.
 *
 *  - Pages, CSS, JS and data files: network first, the cached copy offline.
 *  - Images, icons and the font: cache first (versioned by file name or ?v=).
 *
 * Bump VERSION (and the sw.js?v= number at the end of index.html) whenever
 * index.html changes, so every installed copy drops its old cache.
 */
const VERSION = 'bw-v88';
// The app shell, exactly as index.html requests it, so it opens offline.
const CORE = [
  './',
  './manifest.webmanifest',
  './vendor/supabase-js-2.117.2.js',
  './fonts/plus-jakarta-sans-latin.woff2',
  './icons/icon-192.png?v=70',
  './icons/icon-32.png?v=70',
  './favicon.ico?v=70',
  './profile-icons/standardized/fox.png'
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
      .then(hit => hit || (request.mode === 'navigate' ? caches.match('./') : undefined))
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
  const isFresh = request.mode === 'navigate' || /\.(html|css|js|json|webmanifest|ics)$/.test(url.pathname) || url.pathname.endsWith('/');
  event.respondWith(isFresh ? networkFirst(request) : cacheFirst(request));
});
