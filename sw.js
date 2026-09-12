const CACHE="brighton-weekend-v58-groups-cosmetic";
const CORE=["./","./index.html","./manifest.webmanifest","./favicon.ico","./icons/icon-32.png","./icons/icon-192.png","./icons/icon-512.png","./icons/icon-192-maskable.png","./icons/icon-512-maskable.png","./icons/apple-touch-icon.png","./about.html","./privacy.html","./terms.html","./profile-icons/brown-bear.svg","./profile-icons/red-panda-bear.svg","./profile-icons/giant-panda-bear.svg"];
self.addEventListener("install",event=>{event.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener("activate",event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
async function transformIndex(response){
 if(!response||!response.ok)return response;
 let text=await response.text();
 // Bee was never selected by a user, so remove it outright from the served avatar picker.
 text=text.replace(/'bee',/g,'');
 text=text.replace(/,'bee':'Bee'/g,'');
 // Add the three bear avatars to the picker data.
 text=text.replace(/'winged-lion'\];/,"'winged-lion','brown-bear','red-panda-bear','giant-panda-bear'];");
 text=text.replace(/'winged-lion':'Winged Lion'\};/,"'winged-lion':'Winged Lion','brown-bear':'Brown Bear','red-panda-bear':'Red Panda Bear','giant-panda-bear':'Giant Panda Bear'};");
 // Bear artwork is SVG; the existing artwork remains PNG.
 text=text.replace(/return 'profile-icons\/'+encodeURIComponent\(icon\)+'\.png'/,"return 'profile-icons/'+encodeURIComponent(icon)+(icon.endsWith('-bear')?'.svg':'.png')");
 // Use the secure profile-icon RPC rather than a direct PATCH.
 text=text.replace(/await api\('PATCH','bw_profiles\?user_id=eq\.'\+encodeURIComponent\(authUser\.id\),\{profile_icon:icon\},\{'Prefer':'return=representation'\}\);/,"await rpc('bw_set_profile_icon',{p_user_id:uid(),p_profile_icon:icon});");
 text=text.replace(/Could not save your icon yet\. Please run the profile-icons database update first\./g,'Could not save your icon yet. Please try again.');
 // Cosmetic group-page fixes: keep the onboarding card scrollable and give its final action room.
 text=text.replace(/\.group-step\{display:grid;gap:12px;text-align:left\}/,`.group-step{display:grid;gap:12px;text-align:left}`);
 text=text.replace(/\.group-form button \+ \.group-meta\{margin-top:2px\}/,`.group-form button + .group-meta{margin-top:2px}.group-step{padding-bottom:18px}.welcome-card{max-height:calc(100dvh - 40px);overflow-y:auto}.welcome-card #partyOnBtn{margin-top:8px}`);
 // Put Manage Groups beside the Groups heading and make it a compact coral pill.
 text=text.replace(`<div class="group-panel"><h3 style="margin:12px 0 4px">Groups</h3><p class="note">Manage the groups that shape your Happenings feed.</p>`, `<div class="group-panel"><div class="group-settings-head"><h3>Groups</h3><button id="manageGroups" class="manage-groups-btn">Manage groups</button></div><p class="note">Manage the groups that shape your Happenings feed.</p>`);
 text=text.replace(`<button id="manageGroups" class="secondary">Manage groups</button></div>`, `</div>`);
 text=text.replace(`.settings-card h3{margin:0 0 6px;color:var(--bw-cream)}`, `.settings-card h3{margin:0 0 6px;color:var(--bw-cream)}.group-settings-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:12px 0 5px}.group-settings-head h3{margin:0}.manage-groups-btn{width:auto!important;flex:0 0 auto;padding:9px 13px!important;border-radius:999px!important;background:var(--bw-coral)!important;color:#0B1D2F!important;border:1px solid var(--bw-coral)!important;font-weight:800!important;font-size:.72rem!important;white-space:nowrap}`);
 return new Response(text,{status:response.status,statusText:response.statusText,headers:new Headers(response.headers)});
}
self.addEventListener("fetch",event=>{const req=event.request;if(req.method!=="GET")return;const url=new URL(req.url);if(url.origin!==self.location.origin)return;
 if(url.pathname.endsWith("events.json")){event.respondWith(fetch(req,{cache:"no-store"}).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy));return r}).catch(()=>caches.match(req)));return;}
 if(req.mode==="navigate"||url.pathname.endsWith(".html")){event.respondWith(fetch(req).then(async r=>{const transformed=url.pathname.endsWith("/index.html")||url.pathname.endsWith("/")?await transformIndex(r):r;const copy=transformed.clone();caches.open(CACHE).then(c=>c.put(req,copy));return transformed}).catch(()=>caches.match(req).then(r=>r||caches.match("./index.html"))));return;}
 event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy));return r})));
});
