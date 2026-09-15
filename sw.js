const CACHE="brighton-weekend-v94-assets";
const CORE=["./","./index.html","./manifest.webmanifest","./favicon.ico","./icons/icon-32.png","./icons/icon-192.png","./icons/icon-512.png","./icons/icon-192-maskable.png","./icons/icon-512-maskable.png","./icons/apple-touch-icon.png","./about.html","./privacy.html","./terms.html","./profile-icons/brown-bear.svg","./profile-icons/red-panda-bear.svg","./profile-icons/giant-panda-bear.svg","./profile-icons/moose.jpg","./profile-icons/orange-tabby.jpg","./profile-icons/black-cat.jpg","./profile-icons/fluffy-cat.jpg","./profile-icons/tuxedo-cat.jpg"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));

const SEARCH_UI=`
<style id="bw-search-ui">
#searchTab{padding-bottom:calc(120px + env(safe-area-inset-bottom))}
.bw-search-card{background:#102536;border:1px solid #294657;border-radius:18px;padding:16px;margin:8px 0 18px}
.bw-search-card h2{margin:0 0 5px}.bw-search-card .note{margin:0 0 14px}
.bw-search-input{width:100%;padding:14px 16px;border-radius:14px;border:1px solid #345468;background:#0B1D2F;color:#F3E4C9;outline:none;font-size:16px}
.bw-search-input:focus{border-color:#4DB6AC;box-shadow:0 0 0 3px rgba(77,182,172,.12)}
.bw-filter-label{display:block;font-size:.72rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#A7B5BE;margin:16px 0 8px}
.bw-pills{display:flex;gap:6px;flex-wrap:wrap}.bw-pill{border:1px solid #345468;background:#0F2231;color:#C3D0D6;border-radius:999px;padding:8px 11px;font-size:.72rem;font-weight:700;cursor:pointer}.bw-pill.active{background:#153B39;border-color:#397A72;color:#8FE0D5}
.bw-dates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.bw-date-input{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #345468;background:#0B1D2F;color:#F3E4C9}.bw-search-actions{display:flex;gap:8px;margin-top:16px}.bw-search-actions button{flex:1;padding:11px;border-radius:12px;border:1px solid #FF7767;background:#FF7767;color:#0B1D2F;font-weight:800}.bw-search-actions .secondary{background:#102536;color:#F3E4C9;border-color:#294657}
.bw-results-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:18px 0 8px}.bw-results-head h3{margin:0}.bw-results-count{font-size:.7rem;color:#A7B5BE}.bw-search-result{background:#102536;border:1px solid #294657;border-radius:16px;padding:14px;margin:8px 0}.bw-search-result .title{color:#F3E4C9;font-size:1rem;font-weight:700}.bw-search-result .meta{color:#9FB0BB;margin-top:5px;font-size:.76rem}.bw-search-result .bw-result-date{color:#8FE0D5;font-size:.7rem;font-weight:800;margin-bottom:5px}.bw-search-result .actions{margin-top:10px}.bw-search-result a{display:inline-flex;padding:8px 10px;border-radius:10px;background:#FF7767;color:#0B1D2F;text-decoration:none;font-size:.72rem;font-weight:800}
@media(max-width:430px){.bw-dates{grid-template-columns:1fr}.bw-search-card{padding:14px}}
</style>`;

const SEARCH_SCRIPT=`
<script id="bw-search-script">
(()=>{
 if(window.__bwSearchReady)return; window.__bwSearchReady=true;
 const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
 const DAY_INDEX={Monday:1,Tuesday:2,Wednesday:3,Thursday:4,Friday:5,Saturday:6,Sunday:0};
 let searchEvents=[];
 let selectedDays=new Set(DAYS);
 let rangeStart='',rangeEnd='';
 const $=id=>document.getElementById(id);
 const esc=s=>{const d=document.createElement('div');d.textContent=s||'';return d.innerHTML};
 const dateObj=s=>/^\\d{4}-\\d{2}-\\d{2}$/.test(s||'')?new Date(s+'T12:00:00'):null;
 const today=new Date(); today.setHours(12,0,0,0);
 const dateKey=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
 function endOfWeek(d){const x=new Date(d);x.setDate(x.getDate()+(7-x.getDay())%7);return x}
 function startOfWeek(d){const x=new Date(d);x.setDate(x.getDate()-((x.getDay()+6)%7));return x}
 function setup(){
  const nav=document.querySelector('.nav'); if(!nav||$('searchTab'))return;
  const searchMain=document.createElement('main'); searchMain.id='searchTab'; searchMain.className='wrap app-main hidden';
  searchMain.innerHTML=`<div class="bw-search-card"><h2>Search</h2><div class="note">Find artists, events or venues across Brighton &amp; Hove.</div><input id="bwArtistSearch" class="bw-search-input" type="search" placeholder="Search artists, events or venues" autocomplete="off" aria-label="Search artists, events or venues"><label class="bw-filter-label">Date</label><div class="bw-pills"><button class="bw-pill active" data-preset="weekend">This weekend</button><button class="bw-pill" data-preset="week">This week</button><button class="bw-pill" data-preset="next7">Next 7 days</button><button class="bw-pill" data-preset="custom">Choose dates</button></div><div id="bwCustomDates" class="bw-dates hidden" style="margin-top:9px"><input id="bwFrom" class="bw-date-input" type="date" aria-label="From date"><input id="bwTo" class="bw-date-input" type="date" aria-label="To date"></div><label class="bw-filter-label">Days of the week</label><div id="bwDays" class="bw-pills">${DAYS.map(d=>`<button class="bw-pill active" data-day="${d}">${d.slice(0,3)}</button>`).join('')}</div><div class="bw-search-actions"><button id="bwRunSearch">Search</button><button id="bwClearSearch" class="secondary">Clear</button></div></div><div class="bw-results-head"><h3>Results</h3><span id="bwResultsCount" class="bw-results-count"></span></div><div id="bwResults"><div class="empty">Search the event listings to find something specific.</div></div>`;
  document.body.insertBefore(searchMain,nav);
  const b=document.createElement('button');b.dataset.tab='searchTab';b.innerHTML='<span class="nav-icon">⌕</span> Search';nav.insertBefore(b,nav.children[1]);
  nav.querySelectorAll('button').forEach(x=>{x.addEventListener('click',()=>{if(x.dataset.tab==='searchTab'){loadAndRender();}})});
  $('bwArtistSearch').addEventListener('input',()=>renderResults());
  $('bwRunSearch').onclick=()=>renderResults();
  $('bwClearSearch').onclick=()=>{ $('bwArtistSearch').value=''; selectedDays=new Set(DAYS); setPreset('weekend'); renderResults(); };
  nav.querySelectorAll('button').forEach(x=>x.addEventListener('click',()=>{if(x.dataset.tab!=='searchTab')searchMain.classList.add('hidden')}));
  document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>setPreset(b.dataset.preset));
  document.querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>{const d=b.dataset.day;if(selectedDays.has(d))selectedDays.delete(d);else selectedDays.add(d);b.classList.toggle('active',selectedDays.has(d));renderResults()});
  $('bwFrom').onchange=()=>{rangeStart=$('bwFrom').value;renderResults()}; $('bwTo').onchange=()=>{rangeEnd=$('bwTo').value;renderResults()};
  setPreset('weekend');
 }
 function setPreset(p){
  document.querySelectorAll('[data-preset]').forEach(b=>b.classList.toggle('active',b.dataset.preset===p));
  $('bwCustomDates').classList.toggle('hidden',p!=='custom');
  const base=new Date();base.setHours(12,0,0,0);
  if(p==='weekend'){
   const friday=new Date(base); friday.setDate(friday.getDate()+(5-friday.getDay()+7)%7); rangeStart=dateKey(friday); const sunday=new Date(friday);sunday.setDate(sunday.getDate()+2);rangeEnd=dateKey(sunday); selectedDays=new Set(['Friday','Saturday','Sunday']);
  }else if(p==='week'){
   rangeStart=dateKey(startOfWeek(base));rangeEnd=dateKey(endOfWeek(base));selectedDays=new Set(DAYS);
  }else if(p==='next7'){
   rangeStart=dateKey(base);const x=new Date(base);x.setDate(x.getDate()+6);rangeEnd=dateKey(x);selectedDays=new Set(DAYS);
  }else{return renderResults()}
  document.querySelectorAll('[data-day]').forEach(b=>b.classList.toggle('active',selectedDays.has(b.dataset.day)));
  $('bwFrom').value=rangeStart;$('bwTo').value=rangeEnd;renderResults();
 }
 async function loadAndRender(){
  if(searchEvents.length)return renderResults();
  try{const r=await fetch('events.json?search='+Date.now(),{cache:'no-store'});const j=await r.json();searchEvents=Array.isArray(j.events)?j.events:[];renderResults()}catch(e){$('bwResults').innerHTML='<div class="empty">Could not load events right now.</div>'}
 }
 function renderResults(){
  if(!$('bwResults'))return;
  const q=($('bwArtistSearch').value||'').trim().toLowerCase();
  const from=rangeStart||dateKey(today),to=rangeEnd||rangeStart||dateKey(today);
  let rows=searchEvents.filter(e=>{
   if(!e||!e.title||!e.date)return false; const d=dateObj(e.date);if(!d)return false;
   if(e.date<from||e.date>to)return false;
   const day=DAYS.find(x=>DAY_INDEX[x]===d.getDay());if(selectedDays.size&&!selectedDays.has(day))return false;
   if(q){const hay=[e.title,e.venue,e.venue_display,e.category,e.description,e.type,e.genre,e.tags].filter(Boolean).join(' ').toLowerCase();if(!hay.includes(q))return false}
   return true;
  }).sort((a,b)=>(a.date+(a.time||'')).localeCompare(b.date+(b.time||'')));
  $('bwResultsCount').textContent=rows.length+' event'+(rows.length===1?'':'s');
  if(!rows.length){$('bwResults').innerHTML='<div class="empty">No events match those search options.</div>';return}
  $('bwResults').innerHTML=rows.map(e=>{const d=dateObj(e.date);const day=d.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});return `<article class="bw-search-result"><div class="bw-result-date">${esc(day)}</div><div class="title">${esc(e.title)}</div><div class="meta">${esc(e.venue_display||e.venue||'')}${e.time?' · '+esc(e.time)+(e.finish_time?'–'+esc(e.finish_time):''):''}${e.price?' · '+esc(e.price):''}</div>${e.ticket_url?`<div class="actions"><a href="${esc(e.ticket_url)}" target="_blank" rel="noopener">Tickets ↗</a></div>`:''}</article>`}).join('');
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
</script>`;
 const old=SEARCH_SCRIPT;
 const inject=()=>{};
}
</script>`;

async function transformIndex(response){
 const html=await response.text();
 let patched=html;
 // Discover remains the deliberately simple Friday–Sunday weekend browser.
 patched=patched.replace("const start=getThursday(), end=new Date(friday);end.setDate(end.getDate()+2);", "const start=new Date(friday), end=new Date(friday);end.setDate(end.getDate()+2);");
 patched=patched.replace("const start=getThursday(), end=new Date(start);end.setDate(end.getDate()+3);", "const start=new Date(friday), end=new Date(start);end.setDate(end.getDate()+2);");
 patched=patched.replace("['THURSDAY','FRIDAY','SATURDAY','SUNDAY']", "['FRIDAY','SATURDAY','SUNDAY']");
 // Add a separate Search tab. Discover itself is untouched; Search owns the advanced controls.
 const injection=`${SEARCH_UI}<script id="bw-search-script">(()=>{if(window.__bwSearchReady)return;window.__bwSearchReady=true;const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],DAY_INDEX={Monday:1,Tuesday:2,Wednesday:3,Thursday:4,Friday:5,Saturday:6,Sunday:0};let searchEvents=[],selectedDays=new Set(['Friday','Saturday','Sunday']),rangeStart='',rangeEnd='';const $=id=>document.getElementById(id),esc=s=>{const d=document.createElement('div');d.textContent=s||'';return d.innerHTML},dateObj=s=>/^\\d{4}-\\d{2}-\\d{2}$/.test(s||'')?new Date(s+'T12:00:00'):null,dateKey=d=>d.toISOString().slice(0,10),startOfWeek=d=>{const x=new Date(d);x.setDate(x.getDate()-((x.getDay()+6)%7));return x},endOfWeek=d=>{const x=new Date(d);x.setDate(x.getDate()+(7-x.getDay())%7);return x};function setup(){const nav=document.querySelector('.nav');if(!nav||$('searchTab'))return;const main=document.createElement('main');main.id='searchTab';main.className='wrap app-main hidden';main.innerHTML='<div class="bw-search-card"><h2>Search</h2><div class="note">Find artists, events or venues across Brighton &amp; Hove.</div><input id="bwArtistSearch" class="bw-search-input" type="search" placeholder="Search artists, events or venues" autocomplete="off"><label class="bw-filter-label">Date</label><div class="bw-pills"><button class="bw-pill active" data-preset="weekend">This weekend</button><button class="bw-pill" data-preset="week">This week</button><button class="bw-pill" data-preset="next7">Next 7 days</button><button class="bw-pill" data-preset="custom">Choose dates</button></div><div id="bwCustomDates" class="bw-dates hidden" style="margin-top:9px"><input id="bwFrom" class="bw-date-input" type="date" aria-label="From date"><input id="bwTo" class="bw-date-input" type="date" aria-label="To date"></div><label class="bw-filter-label">Days of the week</label><div id="bwDays" class="bw-pills">'+DAYS.map(d=>'<button class="bw-pill '+(selectedDays.has(d)?'active':'')+'" data-day="'+d+'">'+d.slice(0,3)+'</button>').join('')+'</div><div class="bw-search-actions"><button id="bwRunSearch">Search</button><button id="bwClearSearch" class="secondary">Clear</button></div></div><div class="bw-results-head"><h3>Results</h3><span id="bwResultsCount" class="bw-results-count"></span></div><div id="bwResults"><div class="empty">Loading events…</div></div>';document.body.insertBefore(main,nav);const b=document.createElement('button');b.dataset.tab='searchTab';b.innerHTML='<span class="nav-icon">⌕</span> Search';nav.insertBefore(b,nav.children[1]);document.querySelectorAll('.nav button').forEach(x=>x.addEventListener('click',()=>{if(x.dataset.tab==='searchTab'){main.classList.remove('hidden');load();}else main.classList.add('hidden')}));$('bwArtistSearch').addEventListener('input',render);$('bwRunSearch').onclick=render;$('bwClearSearch').onclick=()=>{ $('bwArtistSearch').value='';setPreset('weekend')};document.querySelectorAll('[data-preset]').forEach(x=>x.onclick=()=>setPreset(x.dataset.preset));document.querySelectorAll('[data-day]').forEach(x=>x.onclick=()=>{selectedDays.has(x.dataset.day)?selectedDays.delete(x.dataset.day):selectedDays.add(x.dataset.day);x.classList.toggle('active',selectedDays.has(x.dataset.day));render()});$('bwFrom').onchange=()=>{rangeStart=$('bwFrom').value;render()};$('bwTo').onchange=()=>{rangeEnd=$('bwTo').value;render()};setPreset('weekend')}
function setPreset(p){document.querySelectorAll('[data-preset]').forEach(x=>x.classList.toggle('active',x.dataset.preset===p));$('bwCustomDates').classList.toggle('hidden',p!=='custom');const base=new Date();base.setHours(12,0,0,0);if(p==='weekend'){const f=new Date(base);f.setDate(f.getDate()+(5-f.getDay()+7)%7);const s=new Date(f);s.setDate(s.getDate()+2);rangeStart=dateKey(f);rangeEnd=dateKey(s);selectedDays=new Set(['Friday','Saturday','Sunday'])}else if(p==='week'){rangeStart=dateKey(startOfWeek(base));rangeEnd=dateKey(endOfWeek(base));selectedDays=new Set(DAYS)}else if(p==='next7'){rangeStart=dateKey(base);const e=new Date(base);e.setDate(e.getDate()+6);rangeEnd=dateKey(e);selectedDays=new Set(DAYS)}else{return render()}document.querySelectorAll('[data-day]').forEach(x=>x.classList.toggle('active',selectedDays.has(x.dataset.day)));$('bwFrom').value=rangeStart;$('bwTo').value=rangeEnd;render()}
async function load(){if(searchEvents.length)return render();try{const r=await fetch('events.json?search='+Date.now(),{cache:'no-store'});const j=await r.json();searchEvents=Array.isArray(j.events)?j.events:[];render()}catch(e){$('bwResults').innerHTML='<div class="empty">Could not load events right now.</div>'}}
function render(){if(!$('bwResults'))return;const q=($('bwArtistSearch').value||'').trim().toLowerCase(),from=rangeStart,to=rangeEnd;const rows=searchEvents.filter(e=>{const d=dateObj(e.date);if(!d||e.date<from||e.date>to)return false;const day=DAYS.find(x=>DAY_INDEX[x]===d.getDay());if(selectedDays.size&&!selectedDays.has(day))return false;if(q&&!([e.title,e.venue,e.venue_display,e.category,e.description,e.type,e.genre,e.tags].filter(Boolean).join(' ').toLowerCase().includes(q)))return false;return true}).sort((a,b)=>(a.date+(a.time||'')).localeCompare(b.date+(b.time||'')));$('bwResultsCount').textContent=rows.length+' event'+(rows.length===1?'':'s');if(!rows.length){$('bwResults').innerHTML='<div class="empty">No events match those search options.</div>';return}$('bwResults').innerHTML=rows.map(e=>{const d=dateObj(e.date);return '<article class="bw-search-result"><div class="bw-result-date">'+esc(d.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'}))+'</div><div class="title">'+esc(e.title)+'</div><div class="meta">'+esc(e.venue_display||e.venue||'')+(e.time?' · '+esc(e.time)+(e.finish_time?'–'+esc(e.finish_time):''):'')+(e.price?' · '+esc(e.price):'')+'</div>'+(e.ticket_url?'<div class="actions"><a href="'+esc(e.ticket_url)+'" target="_blank" rel="noopener">Tickets ↗</a></div>':'')+'</article>'}).join('')}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();})();</script>`;
 patched=patched.replace('</body>',injection+'</body>');
 return new Response(patched,{status:response.status,statusText:response.statusText,headers:response.headers});
}

self.addEventListener("fetch",event=>{
 const req=event.request;
 if(req.method!=="GET")return;
 const url=new URL(req.url);
 if(url.origin!==self.location.origin)return;
 if(url.pathname.endsWith("events.json")){
  event.respondWith(fetch(req,{cache:"no-store"}).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r}).catch(()=>caches.match(req)));
  return;
 }
 if(req.mode==="navigate"||url.pathname.endsWith('.html')){
  event.respondWith(fetch(req,{cache:'no-store'}).then(async r=>{const transformed=(url.pathname.endsWith('/index.html')||url.pathname.endsWith('/'))?await transformIndex(r):r;const c=transformed.clone();caches.open(CACHE).then(x=>x.put(req,c));return transformed}).catch(()=>caches.match(req).then(r=>r||caches.match('./index.html'))));
  return;
 }
 event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r})));
});
