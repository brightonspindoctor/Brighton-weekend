const CACHE="brighton-weekend-v55-auth-icons";
const CORE=["./","./index.html","./manifest.webmanifest","./favicon.ico","./icons/icon-32.png","./icons/icon-192.png","./icons/icon-512.png","./icons/icon-192-maskable.png","./icons/icon-512-maskable.png","./icons/apple-touch-icon.png","./about.html","./privacy.html","./terms.html","./profile-icons/brown-bear.svg","./profile-icons/red-panda-bear.svg","./profile-icons/giant-panda-bear.svg"];
self.addEventListener("install",event=>{event.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener("activate",event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
async function transformIndex(response){
 if(!response||!response.ok)return response;
 let text=await response.text();
 text=text.replace(/'bee',/g,'');
 text=text.replace(/,'bee':'Bee'/g,'');
 text=text.replace(/return 'profile-icons\/'+encodeURIComponent\(icon\)\+'\.png'/,"return 'profile-icons/'+encodeURIComponent(icon)+(icon.endsWith('-bear')?'.svg':'.png')");
 text=text.replace(/await api\('PATCH','bw_profiles\?user_id=eq\.'\+encodeURIComponent\(authUser\.id\),\{profile_icon:icon\},\{'Prefer':'return=representation'\}\);/,"await rpc('bw_set_profile_icon',{p_user_id:uid(),p_profile_icon:icon});");
 text=text.replace(/Could not save your icon yet\. Please run the profile-icons database update first\./g,'Could not save your icon yet. Please try again.');
 return new Response(text,{status:response.status,statusText:response.statusText,headers:new Headers(response.headers)});
}
self.addEventListener("fetch",event=>{const req=event.request;if(req.method!=="GET")return;const url=new URL(req.url);if(url.origin!==self.location.origin)return;
 if(url.pathname.endsWith("events.json")){event.respondWith(fetch(req,{cache:"no-store"}).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy));return r}).catch(()=>caches.match(req)));return;}
 if(req.mode==="navigate"||url.pathname.endsWith(".html")){event.respondWith(fetch(req).then(async r=>{const transformed=url.pathname.endsWith("/index.html")||url.pathname.endsWith("/")?await transformIndex(r):r;const copy=transformed.clone();caches.open(CACHE).then(c=>c.put(req,copy));return transformed}).catch(()=>caches.match(req).then(r=>r||caches.match("./index.html"))));return;}
 event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy));return r})));
});
