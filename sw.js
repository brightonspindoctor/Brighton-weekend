const CACHE="brighton-weekend-v82-avatar-assets";
const CORE=["./","./index.html","./manifest.webmanifest","./favicon.ico","./icons/icon-32.png","./icons/icon-192.png","./icons/icon-512.png","./icons/icon-192-maskable.png","./icons/icon-512-maskable.png","./icons/apple-touch-icon.png","./about.html","./privacy.html","./terms.html","./profile-icons/brown-bear.svg","./profile-icons/red-panda-bear.svg","./profile-icons/giant-panda-bear.svg","./profile-icons/moose.jpg","./profile-icons/orange-tabby.jpg","./profile-icons/golden-retriever.jpg","./profile-icons/black-labrador.jpg","./profile-icons/cockapoo.jpg","./profile-icons/french-bulldog.jpg","./profile-icons/staffy.jpg","./profile-icons/border-collie.jpg","./profile-icons/black-cat.jpg","./profile-icons/fluffy-cat.jpg","./profile-icons/tuxedo-cat.jpg"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));

async function transformIndex(response){
 const html=await response.text();
 const dogFix='<style id="bw-dog-avatar-fix">.profile-icon-option{overflow:hidden}.profile-icon-option img[src*="golden-retriever.jpg"],.profile-icon-option img[src*="black-labrador.jpg"],.profile-icon-option img[src*="cockapoo.jpg"],.profile-icon-option img[src*="french-bulldog.jpg"],.profile-icon-option img[src*="staffy.jpg"],.profile-icon-option img[src*="border-collie.jpg"]{width:100%;height:190%;max-width:none;object-fit:fill;transform:translateY(-31%);}.profile-current img[src*="golden-retriever.jpg"],.profile-current img[src*="black-labrador.jpg"],.profile-current img[src*="cockapoo.jpg"],.profile-current img[src*="french-bulldog.jpg"],.profile-current img[src*="staffy.jpg"],.profile-current img[src*="border-collie.jpg"]{transform:scaleY(1.65);}</style>';
 return new Response(html.replace('</head>',dogFix+'</head>'),{status:response.status,statusText:response.statusText,headers:response.headers});
}

self.addEventListener("fetch",event=>{
 const req=event.request;if(req.method!=="GET")return;
 const url=new URL(req.url);if(url.origin!==self.location.origin)return;
 if(url.pathname.endsWith("events.json")){event.respondWith(fetch(req,{cache:"no-store"}).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r}).catch(()=>caches.match(req)));return}
 if(req.mode==="navigate"||url.pathname.endsWith('.html')){event.respondWith(fetch(req,{cache:'no-store'}).then(async r=>{const transformed=(url.pathname.endsWith('/index.html')||url.pathname.endsWith('/'))?await transformIndex(r):r;const c=transformed.clone();caches.open(CACHE).then(x=>x.put(req,c));return transformed}).catch(()=>caches.match(req).then(r=>r||caches.match('./index.html'))));return}
 event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r})));
});