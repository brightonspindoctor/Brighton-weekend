const CACHE="brighton-weekend-v80-avatar-assets";
const CORE=["./","./index.html","./manifest.webmanifest","./favicon.ico","./icons/icon-32.png","./icons/icon-192.png","./icons/icon-512.png","./icons/icon-192-maskable.png","./icons/icon-512-maskable.png","./icons/apple-touch-icon.png","./about.html","./privacy.html","./terms.html","./profile-icons/brown-bear.svg","./profile-icons/red-panda-bear.svg","./profile-icons/giant-panda-bear.svg","./profile-icons/moose.jpg","./profile-icons/orange-tabby.jpg","./profile-icons/golden-retriever.jpg","./profile-icons/black-labrador.jpg","./profile-icons/cockapoo.jpg","./profile-icons/french-bulldog.jpg","./profile-icons/staffy.jpg","./profile-icons/border-collie.jpg","./profile-icons/black-cat.jpg","./profile-icons/fluffy-cat.jpg","./profile-icons/tuxedo-cat.jpg"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));

async function transformIndex(response){ return response; }

self.addEventListener("fetch",event=>{
 const req=event.request;if(req.method!=="GET")return;
 const url=new URL(req.url);if(url.origin!==self.location.origin)return;
 if(url.pathname.endsWith("events.json")){event.respondWith(fetch(req,{cache:"no-store"}).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r}).catch(()=>caches.match(req)));return}
 if(req.mode==="navigate"||url.pathname.endsWith('.html')){event.respondWith(fetch(req,{cache:'no-store'}).then(async r=>{const transformed=(url.pathname.endsWith('/index.html')||url.pathname.endsWith('/'))?await transformIndex(r):r;const c=transformed.clone();caches.open(CACHE).then(x=>x.put(req,c));return transformed}).catch(()=>caches.match(req).then(r=>r||caches.match('./index.html'))));return}
 event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r})));
});