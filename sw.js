const CACHE="brighton-weekend-v68-avatar-onboarding";
const CORE=["./","./index.html","./manifest.webmanifest","./favicon.ico","./icons/icon-32.png","./icons/icon-192.png","./icons/icon-512.png","./icons/icon-192-maskable.png","./icons/icon-512-maskable.png","./icons/apple-touch-icon.png","./about.html","./privacy.html","./terms.html","./profile-icons/brown-bear.svg","./profile-icons/red-panda-bear.svg","./profile-icons/giant-panda-bear.svg","./profile-icons/raccoon.svg"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));

async function transformIndex(response){
 if(!response||!response.ok)return response;
 let text=await response.text();
 // Avatar catalogue: retire bee and add the new bear/raccoon set.
 text=text.replace(/'bee',/g,'').replace(/,'bee':'Bee'/g,'');
 if(!text.includes("'brown-bear'")) text=text.replace(/'winged-lion'\];/,"'winged-lion','brown-bear','red-panda-bear','giant-panda-bear','raccoon'];");
 if(!text.includes("'brown-bear':'Brown Bear'")) text=text.replace(/'winged-lion':'Winged Lion'\};/,"'winged-lion':'Winged Lion','brown-bear':'Brown Bear','red-panda-bear':'Red Panda','giant-panda-bear':'Giant Panda','raccoon':'Raccoon'};");
 // New assets are SVG wrappers; keep all legacy avatars as PNGs.
 text=text.replace("function iconSrc(icon){return 'profile-icons/'+encodeURIComponent(icon)+'.png'}","function iconSrc(icon){return 'profile-icons/'+encodeURIComponent(icon)+(icon.endsWith('-bear')||icon==='raccoon'?'.svg':'.png')}");
 text=text.replace("await api('PATCH','bw_profiles?user_id=eq.'+encodeURIComponent(authUser.id),{profile_icon:icon},{'Prefer':'return=representation'});","await rpc('bw_set_profile_icon',{p_user_id:uid(),p_profile_icon:icon});");
 text=text.replace('Could not save your icon yet. Please run the profile-icons database update first.','Could not save your icon yet. Please try again.');
 // Handle magic-link callback before reading the session.
 if(!text.includes('bwMagicCallbackHandled')){
  const marker="async function initAuth(){";
  const helper="async function bwMagicCallbackHandled(){const url=new URL(window.location.href);const code=url.searchParams.get('code');if(!code)return;const {error}=await supabase.auth.exchangeCodeForSession(code);if(error)throw error;url.searchParams.delete('code');window.history.replaceState({},document.title,url.pathname+url.search+url.hash);}\n";
  text=text.replace(marker,helper+marker);
 }
 text=text.replace("const {data,error}=await supabase.auth.getSession();\n if(error)throw error;","await bwMagicCallbackHandled();\n const {data,error}=await supabase.auth.getSession();\n if(error)throw error;");
 // Friendly sign-in rate-limit message.
 text=text.replace("msg.textContent='Could not send the sign-in link. '+(err.message||err);btn.disabled=false;input.disabled=false;","const rateLimited=/rate limit exceeded/i.test(err?.message||'');msg.textContent=rateLimited?'We are really busy right now, please try again in an hour':'Could not send the sign-in link. '+(err.message||err);btn.disabled=false;input.disabled=false;");
 // Make Party On require a group.
 text=text.replace("<button type=\"button\" id=\"partyOnBtn\">Party On →</button>","<button type=\"button\" id=\"partyOnBtn\" disabled>Party On →</button><div id=\"partyOnHint\" class=\"group-meta\">Join or create a group to continue.</div>");
 if(!text.includes('function updatePartyOnState')){
  const marker='function finishWelcome(){';
  const helper="function updatePartyOnState(){const btn=$('partyOnBtn'),hint=$('partyOnHint');if(!btn)return;const ready=Array.isArray(groups)&&groups.length>0;btn.disabled=!ready;btn.style.opacity=ready?'1':'.55';btn.style.cursor=ready?'pointer':'not-allowed';if(hint)hint.textContent=ready?'You can join more groups later in Settings.':'Join or create a group to continue.';}\n";
  text=text.replace(marker,helper+marker);
 }
 text=text.replace("function finishWelcome(){\n hide('welcome'); trackVisitor(); renderAll(); renderGroupManager();\n}","function finishWelcome(){\n if(!groups.length){updatePartyOnState();return;}\n hide('welcome'); trackVisitor(); renderAll(); renderGroupManager();\n}");
 text=text.replace("groups=Array.isArray(groups)?groups:[];\n }catch(e){console.warn('Groups unavailable',e);groups=[]}\n await loadGroupMembers();","groups=Array.isArray(groups)?groups:[];\n }catch(e){console.warn('Groups unavailable',e);groups=[]}\n updatePartyOnState();\n await loadGroupMembers();");
 text=text.replace("await loadGroups(); renderOnboardingGroups(); await loadPublicGroups(); renderGroupManager();","await loadGroups(); renderOnboardingGroups(); await loadPublicGroups(); renderGroupManager(); updatePartyOnState();");
 text=text.replace("await loadGroups();renderOnboardingGroups();await loadPublicGroups();renderGroupManager();","await loadGroups();renderOnboardingGroups();await loadPublicGroups();renderGroupManager();updatePartyOnState();");
 // Share invites.
 if(!text.includes('function shareGroupInvite')){
  const marker='function renderOnboardingGroups(){';
  const helper="async function shareGroupInvite(group){if(!group?.id)return;const url=APP_URL+'?join='+encodeURIComponent(group.id)+'&name='+encodeURIComponent(group.name||'');const textBody=`Join ${group.name} on Brighton Weekend`;try{if(navigator.share){await navigator.share({title:'Brighton Weekend',text:textBody,url});return;}}catch(e){if(e?.name==='AbortError')return;}try{await navigator.clipboard.writeText(url);alert('Invite link copied. Send it to your friends.')}catch(e){prompt('Copy this invite link:',url)}}\n";
  text=text.replace(marker,helper+marker);
 }
 text=text.replace("list.innerHTML=groups.length?groups.map(g=>`<div class=\"group-choice\"><span>${g.is_private?'🔒':'◌'}</span><div><strong>${esc(g.name)}</strong><div class=\"group-meta\">${g.member_count||1} member${(g.member_count||1)==1?'':'s'} · ${g.is_private?'Private':'Open'}</div></div></div>`).join(''):'',","list.innerHTML=groups.length?groups.map(g=>`<div class=\"group-choice\"><span>${g.is_private?'🔒':'◌'}</span><div style=\"flex:1\"><strong>${esc(g.name)}</strong><div class=\"group-meta\">${g.member_count||1} member${(g.member_count||1)==1?'':'s'} · ${g.is_private?'Private':'Open'}</div></div><button type=\"button\" class=\"small-btn share-group-btn\" data-group-id=\"${esc(g.id)}\">Share</button></div>`).join(''):'',");
 text=text.replace("$('groupEmpty').textContent=groups.length?'You can belong to as many groups as you like.':'You are not in any groups yet. Create one or join one.';","$('groupEmpty').textContent=groups.length?'You can belong to as many groups as you like.':'You are not in any groups yet. Create one or join one.';document.querySelectorAll('.share-group-btn').forEach(btn=>btn.onclick=()=>shareGroupInvite(groups.find(x=>x.id===btn.dataset.groupId)));");
 // Leave groups.
 if(!text.includes('function leaveGroup')){
  const marker='function renderGroupManager(){';
  const helper="async function leaveGroup(group){if(!group?.id)return;if(!confirm(`Leave ${group.name}?`))return;try{const result=await rpc('bw_leave_group',{p_user_id:uid(),p_group_id:group.id});const row=Array.isArray(result)?result[0]:result;if(!row?.ok)throw new Error(row?.message||'Could not leave group.');await loadGroups();renderGroupManager();renderOnboardingGroups();await loadPublicGroups();updatePartyOnState();await loadGroupMembers();renderAll()}catch(e){alert(e.message||e)}}\n";
  text=text.replace(marker,helper+marker);
 }
 text=text.replace("function renderGroupManager(){\n const el=$('groupManager'); if(!el)return;\n el.innerHTML=groups.length?groups.map(g=>`<div class=\"group-manager-row\"><div><strong>${g.is_private?'🔒':'◌'} ${esc(g.name)}</strong><div class=\"group-meta\">${g.member_count||1} members · ${g.is_private?'Private':'Open'}${g.join_pin?` · PIN <span class=\"pin-display\">${esc(g.join_pin)}</span>`:''}</div></div></div>`).join(''):'<div class=\"group-meta\">No groups yet.</div>';\n}","function renderGroupManager(){\n const el=$('groupManager');if(!el)return;\n el.innerHTML=groups.length?groups.map(g=>`<div class=\"group-manager-row\"><div><strong>${g.is_private?'🔒':'◌'} ${esc(g.name)}</strong><div class=\"group-meta\">${g.member_count||1} members · ${g.is_private?'Private':'Open'}${g.join_pin?` · PIN <span class=\"pin-display\">${esc(g.join_pin)}</span>`:''}</div></div><div class=\"group-row-actions\"><button type=\"button\" class=\"secondary small-btn share-group-btn\" data-group-id=\"${esc(g.id)}\">Share invite</button><button type=\"button\" class=\"danger small-btn leave-group-btn\" data-group-id=\"${esc(g.id)}\">Leave</button></div></div>`).join(''):'<div class=\"group-meta\">No groups yet.</div>';\n document.querySelectorAll('.share-group-btn').forEach(btn=>btn.onclick=()=>shareGroupInvite(groups.find(x=>x.id===btn.dataset.groupId)));document.querySelectorAll('.leave-group-btn').forEach(btn=>btn.onclick=()=>leaveGroup(groups.find(x=>x.id===btn.dataset.groupId)));\n}");
 // Invite links.
 if(!text.includes('bwInviteJoin')){
  const marker='async function openGroupStep(){';
  const helper="async function bwInviteJoin(){const u=new URL(window.location.href),id=u.searchParams.get('join'),invitedName=u.searchParams.get('name')||'';if(!id||!authUser)return false;try{const all=await rpc('bw_public_groups',{p_user_id:uid()});const g=(Array.isArray(all)?all:[]).find(x=>x.id===id);if(g){await joinGroup(id);history.replaceState({},document.title,APP_URL);return true}await loadGroups();renderOnboardingGroups();show('joinGroupPanel');$('privateGroupName').value=invitedName;history.replaceState({},document.title,APP_URL)}catch(e){console.warn('Invite link unavailable',e)}return false}\n";
  text=text.replace(marker,helper+marker);
 }
 text=text.replace("async function openGroupStep(){\n hide('nameStep'); show('groupStep');\n await loadGroups(); renderOnboardingGroups(); await loadPublicGroups();\n}","async function openGroupStep(){\n hide('nameStep'); show('groupStep');\n await loadGroups(); renderOnboardingGroups(); await loadPublicGroups(); updatePartyOnState();\n await bwInviteJoin();\n}");
 // Avatar onboarding: choosing an avatar is now an explicit part of profile creation.
 const avatarHTML='<div id="avatarStep" class="hidden"><h2>Choose your avatar</h2><p>Pick the animal that represents you. You can change it later in Settings.</p><div id="avatarOnboardingGrid" class="profile-icon-grid"></div><div class="avatar-onboarding-actions"><button type="button" class="secondary" id="avatarSurpriseBtn">Surprise me</button><button type="button" id="avatarContinueBtn">Continue →</button></div></div>';
 if(!text.includes('id="avatarStep"')) text=text.replace('<div id="groupStep" class="hidden">',avatarHTML+'<div id="groupStep" class="hidden">');
 if(!text.includes('function renderAvatarOnboarding')){
  const marker='function showWelcome(mode=\'auth\'){';
  const helper="function renderAvatarOnboarding(){const grid=$('avatarOnboardingGrid');if(!grid)return;const icon=PROFILE_ICONS.includes(profileIcon)?profileIcon:'fox';grid.innerHTML=PROFILE_ICONS.map(x=>`<button type=\"button\" class=\"profile-icon-option ${x===icon?'selected':''}\" data-avatar-onboarding=\"${x}\" title=\"${esc(PROFILE_LABELS[x]||x)}\"><img src=\"${iconSrc(x)}\" alt=\"${esc(PROFILE_LABELS[x]||x)}\"></button>`).join('');grid.querySelectorAll('[data-avatar-onboarding]').forEach(b=>b.onclick=async()=>{try{await saveProfileIcon(b.dataset.avatarOnboarding);renderAvatarOnboarding()}catch(e){alert('Could not save your avatar yet. '+(e.message||e))}})}\nfunction showAvatarStep(){hide('nameStep');hide('groupStep');show('avatarStep');renderAvatarOnboarding()}\n";
  text=text.replace(marker,helper+marker);
 }
 text=text.replace("hide('authStep');hide('nameStep');hide('groupStep');hide('createGroupPanel');hide('joinGroupPanel');","hide('authStep');hide('nameStep');hide('avatarStep');hide('groupStep');hide('createGroupPanel');hide('joinGroupPanel');");
 text=text.replace("if(mode==='name' || !name()){show('nameStep');setTimeout(()=>$('nameInput').focus(),50);return}\n openGroupStep();","if(mode==='name' || !name()){show('nameStep');setTimeout(()=>$('nameInput').focus(),50);return}\n if(mode==='avatar'){showAvatarStep();return}\n openGroupStep();");
 // Name -> avatar -> groups.
 text=text.replace("$('nameForm').addEventListener('submit',async e=>{e.preventDefault();const n=$('nameInput').value.trim();if(!n)return;try{await saveProfile(n);await openGroupStep()}catch(err){alert('Could not save your profile. '+(err.message||err))}});","$('nameForm').addEventListener('submit',async e=>{e.preventDefault();const n=$('nameInput').value.trim();if(!n)return;try{await saveProfile(n);showAvatarStep()}catch(err){alert('Could not save your profile. '+(err.message||err))}});");
 // Avatar buttons.
 if(!text.includes("$('avatarContinueBtn').onclick")) text=text.replace("$('partyOnBtn').onclick=finishWelcome;","$('partyOnBtn').onclick=finishWelcome;\n$('avatarContinueBtn').onclick=async()=>{await openGroupStep()};\n$('avatarSurpriseBtn').onclick=async()=>{try{await saveProfileIcon(randomProfileIcon());renderAvatarOnboarding()}catch(e){alert('Could not save your avatar yet. '+(e.message||e))}};");
 // Cosmetics, including a robust vertical gap before Party On and onboarding avatar layout.
 if(!text.includes('bw-group-cosmetics')){
  const css='<style id="bw-group-cosmetics">.welcome-card{max-height:calc(100dvh - 40px);overflow-y:auto}.group-step{padding-bottom:18px}.group-actions{margin-bottom:14px}.group-actions button{margin:0}.group-choice .share-group-btn{margin-left:auto;flex:0 0 auto;width:auto}.group-manager-row .group-row-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:0 0 auto}.group-manager-row .share-group-btn,.group-manager-row .leave-group-btn{white-space:nowrap;width:auto}.leave-group-btn{border-color:#7a4747!important;color:#f0b2ad!important;background:#24191b!important}.group-settings-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.manage-groups-btn{background:#FF7767!important;color:#0B1D2F!important;border-color:#FF7767!important;border-radius:999px!important;padding:8px 12px!important;font-weight:800!important;white-space:nowrap}.party-on-disabled{opacity:.55;cursor:not-allowed}.group-step .group-actions{gap:14px;margin-top:14px}.group-step #partyOnBtn{margin-top:18px!important;display:block;width:100%}.avatar-onboarding-actions{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.avatar-onboarding-actions button{width:100%}</style>';
  text=text.replace('</head>',css+'</head>');
 }
 // Settings group manager heading: keep one clear Manage groups action.
 text=text.replace('<div class="group-panel"><h3 style="margin:12px 0 4px">Groups</h3><p class="note">Manage the groups that shape your Happenings feed.</p><div id="groupManager"></div><button id="manageGroups" class="secondary">Manage groups</button></div>','<div class="group-panel"><div class="group-settings-head"><h3 style="margin:12px 0 4px">Groups</h3><button id="manageGroups" class="manage-groups-btn">Manage groups</button></div><p class="note">Manage the groups that shape your Happenings feed.</p><div id="groupManager"></div></div>');
 return new Response(text,{status:response.status,statusText:response.statusText,headers:new Headers(response.headers)});
}

self.addEventListener("fetch",event=>{
 const req=event.request;if(req.method!=="GET")return;
 const url=new URL(req.url);if(url.origin!==self.location.origin)return;
 if(url.pathname.endsWith("events.json")){event.respondWith(fetch(req,{cache:"no-store"}).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r}).catch(()=>caches.match(req)));return}
 if(req.mode==="navigate"||url.pathname.endsWith('.html')){event.respondWith(fetch(req,{cache:'no-store'}).then(async r=>{const transformed=(url.pathname.endsWith('/index.html')||url.pathname.endsWith('/'))?await transformIndex(r):r;const c=transformed.clone();caches.open(CACHE).then(x=>x.put(req,c));return transformed}).catch(()=>caches.match(req).then(r=>r||caches.match('./index.html'))));return}
 event.respondWith(caches.match(req).then(cached=>cached||fetch(req).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put(req,c));return r})));
});