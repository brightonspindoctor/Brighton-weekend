const CACHE="brighton-weekend-v59-auth-bears";
const CORE=["./","./index.html","./manifest.webmanifest","./favicon.ico","./icons/icon-32.png","./icons/icon-192.png","./icons/icon-512.png","./icons/icon-192-maskable.png","./icons/icon-512-maskable.png","./icons/apple-touch-icon.png","./about.html","./privacy.html","./terms.html","./profile-icons/brown-bear.svg","./profile-icons/red-panda-bear.svg","./profile-icons/giant-panda-bear.svg"];
self.addEventListener("install",event=>{event.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener("activate",event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});

async function transformIndex(response){
 if(!response||!response.ok)return response;
 let text=await response.text();

 // Remove Bee completely. No existing user has selected it.
 text=text.replace(/'bee',/g,'').replace(/,'bee':'Bee'/g,'');

 // Add the three bear avatars to the picker.
 if(!text.includes("'brown-bear'")) text=text.replace(/'winged-lion'\];/,"'winged-lion','brown-bear','red-panda-bear','giant-panda-bear'];");
 if(!text.includes("'brown-bear':'Brown Bear'")) text=text.replace(/'winged-lion':'Winged Lion'\};/,"'winged-lion':'Winged Lion','brown-bear':'Brown Bear','red-panda-bear':'Red Panda Bear','giant-panda-bear':'Giant Panda Bear'};");

 // The three bear assets are SVG files; all existing icons remain PNG.
 text=text.replace("function iconSrc(icon){return 'profile-icons/'+encodeURIComponent(icon)+'.png'}","function iconSrc(icon){return 'profile-icons/'+encodeURIComponent(icon)+(icon.endsWith('-bear')?'.svg':'.png')}");

 // Save the profile icon through the authenticated RPC.
 text=text.replace("await api('PATCH','bw_profiles?user_id=eq.'+encodeURIComponent(authUser.id),{profile_icon:icon},{'Prefer':'return=representation'});","await rpc('bw_set_profile_icon',{p_user_id:uid(),p_profile_icon:icon});");
 text=text.replace('Could not save your icon yet. Please run the profile-icons database update first.','Could not save your icon yet. Please try again.');

 // Ensure the magic-link option exists in the welcome screen, including on older cached HTML.
 if(!text.includes('id="magicLinkForm"')){
   const marker='<button type="button" id="googleSignInBtn" class="google-btn">Continue with Google</button>';
   const magic='<div class="magic-link-divider"><span>or</span></div><form id="magicLinkForm" class="magic-link-form"><input id="magicLinkEmail" type="email" autocomplete="email" inputmode="email" placeholder="Your email address" aria-label="Email address" required><button type="submit" id="magicLinkBtn" class="magic-link-btn">Email me a sign-in link</button></form><p id="authMessage" class="group-meta"></p>';
   text=text.replace(marker,marker+magic);
 }
 if(!text.includes("signInWithMagicLink(input.value)")){
   const marker="$('googleSignInBtn').addEventListener('click'";
   const handler="$('magicLinkForm').addEventListener('submit',async e=>{e.preventDefault();const btn=$('magicLinkBtn'),input=$('magicLinkEmail'),msg=$('authMessage');try{btn.disabled=true;input.disabled=true;msg.textContent='Sending your sign-in link…';await signInWithMagicLink(input.value);msg.textContent='Check your email — your sign-in link is on its way.';}catch(err){msg.textContent='Could not send the sign-in link. '+(err.message||err);btn.disabled=false;input.disabled=false;}});\n";
   text=text.replace(marker,handler+marker);
 }
 if(!text.includes('.magic-link-form{')){
   const css='<style>.magic-link-divider{display:flex;align-items:center;gap:10px;margin:12px 0;color:#A7B5BE;font-size:.75rem}.magic-link-divider:before,.magic-link-divider:after{content:"";height:1px;background:#294657;flex:1}.magic-link-form{display:grid;gap:10px}.magic-link-form input{width:100%;padding:14px 16px;border:1px solid #345468;border-radius:999px;background:#0B1D2F;color:#F3E4C9;font:inherit;outline:none}.magic-link-form button{width:100%;padding:13px 16px;border:1px solid #FF7767;border-radius:999px;background:#FF7767;color:#0B1D2F;font:800 1rem var(--font-ui);cursor:pointer}.magic-link-form button:disabled{opacity:.65;cursor:wait}</style>';
   text=text.replace('</head>',css+'</head>');
 }
 return new Response(text,{status:response.status,statusText:response.statusText,headers:new Headers(response.headers)});
}

self.addEventListener("fetch",event=>{
 const req=event.request;if(req.method!=="GET")return;
 const url=new URL(req.url);if(url.origin!==self.location.origin)return;
 if(url.pathname.endsWith("events.json")){
   event.respondWith(fetch(req,{cache:"no-store"}).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy));return r}).catch(()=>caches.match(req)));return;
 }
 if(req.mode==="navigate"||url.pathname.endsWith(".html")){
   event.respondWith(fetch(req).then(async r=>{const transformed=(url.pathname.endsWith("/index.html")||url.pathname.endsWith("/"))?await transformIndex(r):r;const copy=transformed.clone();caches.open(CACHE).then(c=>c.put(req,copy));return transformed}).catch(()=>caches.match(req).then(r=>r||caches.match("./index.html"))));return;
 }
 event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy));return r})));
});
