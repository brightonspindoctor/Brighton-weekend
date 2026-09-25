/* Brighton Weekend app logic. Loaded by index.html after supabase-js. */
(() => {
'use strict';
const SUPABASE_URL='https://zqvccsnfrkrtcsitfwcd.supabase.co';
const SUPABASE_KEY='sb_publishable_IyzJ6iCrIIkCtYBhNkQUog_GelEFKo1';
const supabase=window.supabase.createClient(SUPABASE_URL,SUPABASE_KEY,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true}});
let authUser=null;
let authSession=null;
let profileName='';
let profileIcon='';
let profileIconsByUser={};
const PROFILE_ICONS=['fox','badger','otter','hedgehog','squirrel','rabbit','deer','seagull','pigeon','kingfisher','owl','raven','cat','dog','dolphin','shark','whale','octopus','crab','starfish','butterfly','dragonfly','ladybird','moth','beetle','spider','praying-mantis','grasshopper','firefly','snail','ant','wasp','fly','cicada','caterpillar','stick-insect','shield-bug','moth-pink','mushroom','clover','fern','sunflower','lavender','oak-leaf','cherry-blossom','holly','pine-tree','bonsai','unicorn','dragon','phoenix','griffin','mermaid','fairy','wizard','ghost','alien','planet','pegasus','forest-spirit','moon-hare','leviathan','ice-dragon','sky-dragon','sea-serpent','dire-wolf','winged-lion','brown-bear','red-panda-bear','giant-panda-bear','orange-tabby','black-cat','fluffy-cat','tuxedo-cat'];
const PROFILE_LABELS={'fox':'Fox','badger':'Badger','otter':'Otter','hedgehog':'Hedgehog','squirrel':'Squirrel','rabbit':'Rabbit','deer':'Deer','seagull':'Seagull','pigeon':'Pigeon','kingfisher':'Kingfisher','owl':'Owl','raven':'Raven','cat':'Cat','dog':'Dog','dolphin':'Dolphin','shark':'Shark','whale':'Whale','octopus':'Octopus','crab':'Crab','starfish':'Starfish','butterfly':'Butterfly','dragonfly':'Dragonfly','ladybird':'Ladybird','moth':'Moth','beetle':'Beetle','spider':'Spider','praying-mantis':'Praying Mantis','grasshopper':'Grasshopper','firefly':'Firefly','snail':'Snail','ant':'Ant','wasp':'Wasp','fly':'Fly','cicada':'Cicada','caterpillar':'Caterpillar','stick-insect':'Stick Insect','shield-bug':'Shield Bug','moth-pink':'Moth','mushroom':'Mushroom','clover':'Clover','fern':'Fern','sunflower':'Sunflower','lavender':'Lavender','oak-leaf':'Oak Leaf','cherry-blossom':'Cherry Blossom','holly':'Holly','pine-tree':'Pine Tree','bonsai':'Bonsai','unicorn':'Unicorn','dragon':'Dragon','phoenix':'Phoenix','griffin':'Griffin','mermaid':'Mermaid','fairy':'Fairy','wizard':'Wizard','ghost':'Ghost','alien':'Alien','planet':'Planet','pegasus':'Pegasus','forest-spirit':'Forest Spirit','moon-hare':'Moon Hare','leviathan':'Leviathan','ice-dragon':'Ice Dragon','sky-dragon':'Sky Dragon','sea-serpent':'Sea Serpent','dire-wolf':'Dire Wolf','winged-lion':'Winged Lion','brown-bear':'Brown Bear','red-panda-bear':'Red Panda','giant-panda-bear':'Giant Panda','orange-tabby':'Orange Tabby','black-cat':'Black Cat','fluffy-cat':'Fluffy Cat','tuxedo-cat':'Tuxedo Cat'};
const VENUES=["Brighton Centre","Brighton Dome","CHALK","Concorde 2","The Old Market","Green Door Store","Volks","Quarters","Patterns","DUST","Komedia","The Forge Comedy Club","Theatre Royal Brighton","The Hope & Ruin","The Prince Albert","A L P H A B E T","The Pipeline","Brighton Racecourse","The Gladstone","Babble","Amex Stadium","Shelter Hall","Other"];const COMEDY_VENUES=["Brighton Centre","Brighton Dome","The Old Market","Komedia","The Forge Comedy Club","Theatre Royal Brighton"];const VENUE_ALIASES={"Brighton Dome - Concert Hall":"Brighton Dome"};
const $=id=>document.getElementById(id);
let events=[], attendance=[], groupHappenings=[], groups=[], groupMembers=[], customEvents=[];
const savedVenues=JSON.parse(localStorage.getItem('bw_venues')||'null');
// Persist venue preferences exactly as the user selected them. Do not merge newly added venues into an existing saved list.
let enabled=Array.isArray(savedVenues)?Array.from(new Set(savedVenues.filter(v=>VENUES.includes(v)))):VENUES.slice();
function uid(){return authUser?.id||''}
function name(){return profileName||localStorage.getItem('bw_name')||''}
async function loadProfile(){
 if(!authUser){profileName='';profileIcon='';return false}
 try{
  let rows;
  try{rows=await api('GET','bw_profiles?select=display_name,email,profile_icon&user_id=eq.'+encodeURIComponent(authUser.id));}
  catch(e){rows=await api('GET','bw_profiles?select=display_name,email&user_id=eq.'+encodeURIComponent(authUser.id));}
  if(Array.isArray(rows)&&rows[0]){
   profileName=rows[0].display_name||'';
   profileIcon=PROFILE_ICONS.includes(rows[0].profile_icon)?rows[0].profile_icon:'';
   localStorage.setItem('bw_name',profileName);
   if(profileIcon)localStorage.setItem('bw_profile_icon_'+authUser.id,profileIcon);
   $('accountEmail').textContent=authUser.email||rows[0].email||'';
   if(!profileIcon){profileIcon=localStorage.getItem('bw_profile_icon_'+authUser.id)||randomProfileIcon();try{await saveProfileIcon(profileIcon)}catch(e){console.warn('Profile icon save unavailable',e)}}
   renderProfileIconSettings();
   return !!profileName
  }
 }catch(e){console.warn('Profile load unavailable',e)}
 profileName=localStorage.getItem('bw_name')||'';
 profileIcon=localStorage.getItem('bw_profile_icon_'+authUser.id)||randomProfileIcon();
 if($('accountEmail'))$('accountEmail').textContent=authUser.email||'';
 renderProfileIconSettings();
 return false;
}
function randomProfileIcon(){return PROFILE_ICONS[Math.floor(Math.random()*PROFILE_ICONS.length)]}
const PROFILE_ICON_FILES={"fox":"standardized/fox.png","badger":"standardized/badger.png","otter":"standardized/otter.png","hedgehog":"standardized/hedgehog.png","squirrel":"standardized/squirrel.png","rabbit":"standardized/rabbit.png","deer":"standardized/deer.png","seagull":"standardized/seagull.png","pigeon":"standardized/pigeon.png","kingfisher":"standardized/kingfisher.png","owl":"standardized/owl.png","raven":"standardized/raven.png","cat":"standardized/cat.png","dog":"standardized/dog.png","dolphin":"standardized/dolphin.png","shark":"standardized/shark.png","whale":"standardized/whale.png","octopus":"standardized/octopus.png","crab":"standardized/crab.png","starfish":"standardized/starfish.png","butterfly":"standardized/butterfly.png","dragonfly":"standardized/dragonfly.png","ladybird":"standardized/ladybird.png","moth":"standardized/moth.png","beetle":"standardized/beetle.png","spider":"standardized/spider.png","praying-mantis":"standardized/praying-mantis.png","grasshopper":"standardized/grasshopper.png","firefly":"standardized/firefly.png","snail":"standardized/snail.png","ant":"standardized/ant.png","wasp":"standardized/wasp.png","fly":"standardized/fly.png","cicada":"standardized/cicada.png","caterpillar":"standardized/caterpillar.png","stick-insect":"standardized/stick-insect.png","shield-bug":"standardized/shield-bug.png","moth-pink":"standardized/moth-pink.png","mushroom":"standardized/mushroom.png","clover":"standardized/clover.png","fern":"standardized/fern.png","sunflower":"standardized/sunflower.png","lavender":"standardized/lavender.png","oak-leaf":"standardized/oak-leaf.png","cherry-blossom":"standardized/cherry-blossom.png","holly":"standardized/holly.png","pine-tree":"standardized/pine-tree.png","bonsai":"standardized/bonsai.png","unicorn":"standardized/unicorn.png","dragon":"standardized/dragon.png","phoenix":"standardized/phoenix.png","griffin":"standardized/griffin.png","mermaid":"standardized/mermaid.png","fairy":"standardized/fairy.png","wizard":"standardized/wizard.png","ghost":"standardized/ghost.png","alien":"standardized/alien.png","planet":"standardized/planet.png","pegasus":"standardized/pegasus.png","forest-spirit":"forest-spirit.webp","moon-hare":"moon-hare.webp","leviathan":"leviathan.webp","ice-dragon":"standardized/ice-dragon.png","sky-dragon":"standardized/sky-dragon.png","sea-serpent":"standardized/sea-serpent.png","dire-wolf":"standardized/dire-wolf.png","winged-lion":"standardized/winged-lion.png","brown-bear":"brown-bear.svg","red-panda-bear":"red-panda-bear.svg","giant-panda-bear":"giant-panda-bear.svg","orange-tabby":"standardized/orange-tabby.png","black-cat":"standardized/black-cat.png","fluffy-cat":"standardized/fluffy-cat.png","tuxedo-cat":"standardized/tuxedo-cat.png"};
function iconSrc(icon){
  const file=PROFILE_ICON_FILES[icon]||(icon+'.png');
  return 'profile-icons/'+file.split('/').map(encodeURIComponent).join('/');
}
function userIcon(iconUserId){const icon=profileIconsByUser[iconUserId]||((iconUserId===uid())?profileIcon:'');return icon||'fox'}
async function saveProfileIcon(icon){
 if(!authUser||!PROFILE_ICONS.includes(icon))return;
 await api('PATCH','bw_profiles?user_id=eq.'+encodeURIComponent(authUser.id),{profile_icon:icon},{'Prefer':'return=representation'});
 profileIcon=icon;profileIconsByUser[authUser.id]=icon;localStorage.setItem('bw_profile_icon_'+authUser.id,icon);renderProfileIconSettings();renderAll();
}
function renderProfileIconSettings(){
 const current=$('currentProfileIcon'),nameEl=$('currentProfileIconName'),grid=$('profileIconGrid');
 if(!current||!grid)return;
 const icon=PROFILE_ICONS.includes(profileIcon)?profileIcon:'fox';
 current.src=iconSrc(icon);current.alt=(PROFILE_LABELS[icon]||icon)+' profile icon';
 nameEl.textContent=PROFILE_LABELS[icon]||icon;
 grid.innerHTML=PROFILE_ICONS.map(x=>{const mystic=['unicorn','dragon','phoenix','griffin','mermaid','fairy','wizard','ghost','alien','planet','pegasus','forest-spirit','moon-hare','leviathan','ice-dragon','sky-dragon','sea-serpent','dire-wolf','winged-lion'].includes(x);const bear=['brown-bear','red-panda-bear','giant-panda-bear'].includes(x);const classes=['profile-icon-option',x===icon?'selected':'',mystic?'profile-mystic':'',bear?'profile-bear':''].filter(Boolean).join(' ');return `<button type="button" class="${classes}" data-profile-icon="${x}" title="${esc(PROFILE_LABELS[x]||x)}"><img src="${iconSrc(x)}" alt="${esc(PROFILE_LABELS[x]||x)}"></button>`}).join('');
 grid.querySelectorAll('[data-profile-icon]').forEach(b=>b.onclick=async()=>{const x=b.dataset.profileIcon;try{await saveProfileIcon(x)}catch(e){alert('Could not save your icon yet. Please run the profile-icons database update first.')}});
}
async function loadProfileIcons(){
 profileIconsByUser={};
 if(!authUser)return;
 try{const rows=await rpc('bw_profile_icons_for_user',{p_user_id:uid()});(Array.isArray(rows)?rows:[]).forEach(x=>{if(x.user_id&&PROFILE_ICONS.includes(x.profile_icon))profileIconsByUser[x.user_id]=x.profile_icon});}
 catch(e){console.warn('Profile icons unavailable',e)}
 if(profileIcon)profileIconsByUser[uid()]=profileIcon;
}
async function saveProfile(displayName){
 const clean=displayName.trim(); if(!clean||!authUser) return;
 if(!PROFILE_ICONS.includes(profileIcon))profileIcon=randomProfileIcon();
 await api('POST','bw_profiles',{user_id:authUser.id,email:authUser.email,display_name:clean,profile_icon:profileIcon},{'Prefer':'resolution=merge-duplicates,return=representation'});
 profileName=clean;localStorage.setItem('bw_profile_icon_'+authUser.id,profileIcon);profileIconsByUser[authUser.id]=profileIcon;localStorage.setItem('bw_name',clean);$('accountEmail').textContent=authUser.email||'';
}
const APP_URL='https://brightonspindoctor.github.io/Brighton-weekend/';
async function signInWithGoogle(){
 const {error}=await supabase.auth.signInWithOAuth({
   provider:'google',
   options:{redirectTo:APP_URL}
 });
 if(error)throw error;
}
async function signInWithMagicLink(email){
 const clean=email.trim().toLowerCase();
 if(!clean)throw new Error('Enter your email address.');
 const {error}=await supabase.auth.signInWithOtp({
   email:clean,
   options:{emailRedirectTo:APP_URL}
 });
 if(error)throw error;
}
async function initAuth(){
 const {data,error}=await supabase.auth.getSession();
 if(error)throw error;
 authSession=data.session||null;
 authUser=authSession?.user||null;
 supabase.auth.onAuthStateChange((event,session)=>{
  const previousId=authUser?.id||'';
  authSession=session||null;authUser=session?.user||null;
  // TOKEN_REFRESHED / INITIAL_SESSION / USER_UPDATED only refresh the stored session.
  if(event==='SIGNED_OUT'){setTimeout(()=>showWelcome('auth'),0);return}
  if(event==='SIGNED_IN'&&authUser&&authUser.id!==previousId){
   setTimeout(()=>bootstrapAuthed().then(loadUserData).catch(console.warn),0);
  }
 });
 if(authUser) await bootstrapAuthed(); else showWelcome('auth');
}
async function bootstrapAuthed(){
 const hasProfile=await loadProfile();
 if($('authStep'))hide('authStep');
 if(!hasProfile){showWelcome('name');return;}
 await loadGroups();
 await loadProfileIcons();
 if(groups.length) hide('welcome'); else showWelcome('groups');
 trackVisitor();
}
function dateKey(d){const y=d.getFullYear(),m=String(d.getMonth()+1).padStart(2,'0'),day=String(d.getDate()).padStart(2,'0');return `${y}-${m}-${day}`}
function parseEventDate(value){if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return null;const d=new Date(value+'T12:00:00');return Number.isNaN(d.getTime())?null:d}
function renderAll(){render();renderComedy();renderPeople();}
// Weeks run Monday to Sunday. On a Saturday or Sunday the current week is still shown.
function getMonday(from=new Date()){const d=new Date(from);d.setHours(12,0,0,0);d.setDate(d.getDate()-((d.getDay()+6)%7));return d}
let weekStart=getMonday();
const DAY_NAMES=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const DAYS_KEY='bw_interest_days';
function selectedDays(){try{const x=JSON.parse(localStorage.getItem(DAYS_KEY)||'null');return Array.isArray(x)&&x.length?new Set(x.map(Number)):new Set([0,1,2,3,4,5,6])}catch(e){return new Set([0,1,2,3,4,5,6])}}
// Days already gone are skipped so the current week starts at today.
function weekDays(){const today=todayKey(),chosen=selectedDays();return DAY_NAMES.map((label,i)=>{const d=new Date(weekStart);d.setDate(d.getDate()+i);return {label,index:i,date:d,key:dateKey(d)}}).filter(x=>chosen.has(x.index)&&x.key>=today)}
function dayHeading(day){return `<h3 class="day">${day.label} <span>${day.date.toLocaleDateString('en-GB',{day:'numeric',month:'long'})}</span></h3>`}
function todayKey(){return dateKey(new Date())}
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML.replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function safeUrl(u){try{const x=new URL(String(u||''),location.href);return (x.protocol==='https:'||x.protocol==='http:')?x.href:''}catch(e){return ''}}
function people(id,status){return attendance.filter(x=>x.event_id===id&&x.status===status)}
function groupPeople(id,status){return groupHappenings.filter(x=>x.event_id===id&&x.status===status)}
function uniqueGroupPeopleCount(id,status){const ids=new Set(groupPeople(id,status).map(x=>x.user_id).filter(Boolean)); const mine=attendance.find(x=>x.event_id===id&&x.user_id===uid()&&x.status===status); if(mine)ids.add(uid()); return ids.size}
function canonicalVenue(v){return VENUE_ALIASES[v]||v}
function venueVisible(e){const venue=canonicalVenue(e.venue);return venue==='Other'||enabled.includes(venue)}
function show(el){$(el).classList.remove('hidden')}
function hide(el){$(el).classList.add('hidden')}

async function api(method,path,body,extraHeaders={}){
 const r=await fetch(SUPABASE_URL+'/rest/v1/'+path,{
  method,
  headers:{apikey:SUPABASE_KEY,Authorization:'Bearer '+(authSession?.access_token||SUPABASE_KEY),'Content-Type':'application/json','Prefer':'return=representation',...extraHeaders},
  body:body===undefined?undefined:JSON.stringify(body)
 });
 if(!r.ok) throw new Error(await r.text());
 if(r.status===204) return [];
 const t=await r.text(); return t?JSON.parse(t):[];
}
async function rpc(fn,body){
 return api('POST','rpc/'+fn,body);
}

async function loadCustomEvents(){
 try{
  const rows=await api('GET','bw_custom_events?select=id,title,date,venue,venue_detail,time,finish_time,price,status,ticket_url,category,created_by,created_by_name,created_at&order=date.asc,time.asc');
  customEvents=Array.isArray(rows)?rows:[];
 }catch(e){console.warn('Custom events unavailable',e);customEvents=[]}
}
function mergeEvents(base){
 const seen=new Set(), merged=[];
 [...base,...customEvents.map(e=>({...e,source:'community',is_custom:true}))].forEach(e=>{
  if(!e||!e.id||seen.has(e.id)||!parseEventDate(e.date)||!e.title||!e.venue)return;
  seen.add(e.id);
  if(e.venue==='Other' && e.venue_detail)e.venue_display='Other · '+e.venue_detail; else e.venue_display=canonicalVenue(e.venue);
  merged.push(e);
 });
 return merged;
}
async function addCustomEvent(){
 if(!name()){showWelcome('name');return}
 const title=$('customTitle').value.trim(), date=$('customDate').value, venue=$('customVenue').value, venueDetail=$('customVenueDetail').value.trim(), time=$('customTime').value, finish=$('customFinish').value, price=$('customPrice').value.trim(), ticket=$('customTicket').value.trim(), category=$('customCategory').value, description=$('customDescription').value.trim();
 if(!title||!date||!venue)return alert('Please add a title, date and venue.');
 if(venue==='Other'&&!venueDetail)return alert('Please tell us the other venue.');
 if(!parseEventDate(date))return alert('Please choose a valid date.');
 if(ticket&&!safeUrl(ticket))return alert('Ticket links must start with https:// or http://');
 try{
  const payload={title,date,venue,venue_detail:venue==='Other'?venueDetail:null,time:time||null,finish_time:finish||null,price:price||null,status:'',ticket_url:ticket||null,category:category||'Other',description:description||null,created_by:uid(),created_by_name:name()};
  await api('POST','bw_custom_events',payload);
  await loadCustomEvents();
  events=mergeEvents(events.filter(e=>!e.is_custom));
  ['customTitle','customDate','customTime','customFinish','customPrice','customTicket','customDescription','customVenueDetail'].forEach(id=>$(id).value='');
  $('customVenue').value=''; $('customCategory').value='Other'; toggleOtherVenue();
  $('customEventPanel').classList.add('collapsed');
  $('toggleCustomEvent').textContent='＋ Add event';
  renderAll();
  alert('Added to Brighton Weekend.');
 }catch(e){alert('Could not add that event. '+e.message)}
}
function toggleOtherVenue(){
 const other=$('customVenue')?.value==='Other';
 $('customVenueDetailWrap')?.classList.toggle('hidden',!other);
}
async function loadAttendance(){
 if(!uid()){attendance=[];return}
 try{attendance=await api('GET','event_interest?select=event_id,user_name,status,user_id&user_id=eq.'+encodeURIComponent(uid()))}catch(e){console.warn('Social layer unavailable',e)}
}
async function loadGroups(){
 if(!name()) return;
 try{
  groups=await rpc('bw_my_groups',{p_user_id:uid()});
  groups=Array.isArray(groups)?groups:[];
 }catch(e){console.warn('Groups unavailable',e);groups=[]}
 await loadGroupMembers();
}
async function loadGroupMembers(){
 if(!groups.length){groupMembers=[];return}
 try{
  groupMembers=await rpc('bw_group_members_for_user',{p_user_id:uid()});
  groupMembers=Array.isArray(groupMembers)?groupMembers:[];
 }catch(e){console.warn('Group member list unavailable',e);groupMembers=[]}
}
function happeningsSignature(rows){
 return rows.map(x=>[x.group_id,x.event_id,x.user_id,x.status].join(':')).sort().join('|');
}
function markHappeningsSeen(){
 const current=happeningsSignature(groupHappenings);
 if(current){
  localStorage.setItem('bw_happenings_seen_'+uid(),current);
  localStorage.removeItem('bw_happenings_mark_pending_'+uid());
 }else{
  localStorage.setItem('bw_happenings_mark_pending_'+uid(),'1');
 }
 updateHappeningsBadge();
}
function updateHappeningsBadge(){
 const tab=document.querySelector('.nav button[data-tab="peopleTab"]');
 if(!tab)return;
 const seen=localStorage.getItem('bw_happenings_seen_'+uid())||'';
 const current=happeningsSignature(groupHappenings);
 const hasNew=!!current && current!==seen;
 tab.classList.toggle('has-new',hasNew);
}
async function loadGroupHappenings(){
 if(!groups.length){groupHappenings=[];return}
 try{
  groupHappenings=await rpc('bw_shared_happenings',{p_user_id:uid()});
  groupHappenings=Array.isArray(groupHappenings)?groupHappenings:[];
 }catch(e){console.warn('Group happenings unavailable',e);groupHappenings=[]}
 if(groupHappenings.length && localStorage.getItem('bw_happenings_mark_pending_'+uid())==='1'){
  localStorage.setItem('bw_happenings_seen_'+uid(),happeningsSignature(groupHappenings));
  localStorage.removeItem('bw_happenings_mark_pending_'+uid());
 }
 updateHappeningsBadge();
}
function trackVisitor(){
 api('POST','app_visitors',{user_id:uid(),display_name:name()},{'Prefer':'resolution=merge-duplicates,return=minimal'}).catch(()=>{});
}

function renderOnboardingGroups(){
 const list=$('onboardingGroups');
 list.innerHTML=groups.length?groups.map(g=>`<div class="group-choice"><span>${g.is_private?'🔒':'◌'}</span><div><strong>${esc(g.name)}</strong><div class="group-meta">${g.member_count||1} member${(g.member_count||1)==1?'':'s'} · ${g.is_private?'Private':'Open'}</div></div></div>`).join(''):'';
 $('groupEmpty').textContent=groups.length?'You can belong to as many groups as you like.':'You are not in any groups yet. Create one or join one.';
}
async function loadPublicGroups(){
 try{
  const data=await rpc('bw_public_groups',{p_user_id:uid()});
  $('publicGroupSelect').innerHTML='<option value="">Choose an open group…</option>'+data.map(g=>`<option value="${esc(g.id)}">${esc(g.name)} · ${g.member_count} members</option>`).join('');
 }catch(e){console.warn(e)}
}
async function handleGroupInvite(){
 const q=new URLSearchParams(window.location.search);
 const groupId=q.get('group_invite');
 if(!groupId||!authUser||!name())return false;
 const groupName=q.get('group_name')||'this group';
 const pin=q.get('group_pin')||null;
 if(!confirm(`Join ${groupName}?`))return false;
 await joinGroup(groupId,pin,groupName);
 const clean=window.location.pathname+window.location.hash;
 window.history.replaceState({},document.title,clean);
 return true;
}
async function openGroupStep(){
 hide('nameStep'); show('groupStep');
 await loadGroups(); renderOnboardingGroups(); await loadPublicGroups();
 await handleGroupInvite();
}
function showWelcome(mode='auth'){
 show('welcome');
 $('nameInput').value=name();
 hide('authStep');hide('nameStep');hide('groupStep');hide('createGroupPanel');hide('joinGroupPanel');
 if(mode==='auth' || !authUser){show('authStep');return}
 if(mode==='name' || !name()){show('nameStep');setTimeout(()=>$('nameInput').focus(),50);return}
 openGroupStep();
}
function finishWelcome(){
 hide('welcome'); trackVisitor(); renderAll(); renderGroupManager();
}
async function createGroup(){
 const n=$('newGroupName').value.trim(), privacy=$('newGroupPrivacy').value;
 if(!n){alert('Please give your group a name.');return}
 try{
  const data=await rpc('bw_create_group',{p_user_id:uid(),p_user_name:name(),p_name:n,p_is_private:privacy==='private'});
  const g=Array.isArray(data)?data[0]:data;
  $('newGroupName').value='';
  if(g?.join_pin) alert(`Private group created. Share this PIN with friends: ${g.join_pin}`);
  await loadGroups();renderOnboardingGroups();await loadPublicGroups();renderGroupManager();
 }catch(e){alert('Could not create group. '+e.message)}
}
async function joinGroup(groupId,pin=null,privateName=null){
 try{
  const data=await rpc('bw_join_group',{p_user_id:uid(),p_user_name:name(),p_group_id:groupId||null,p_pin:pin,p_group_name:privateName||null});
  const r=Array.isArray(data)?data[0]:data;
  if(!r?.ok) throw new Error(r?.message||'Could not join group');
  await loadGroups();renderOnboardingGroups();await loadPublicGroups();renderGroupManager();
  hide('joinGroupPanel');
 }catch(e){alert('Could not join group. '+e.message)}
}
async function leaveGroup(groupId,groupName,btn){
 if(!groupId)return;
 if(!confirm(`Leave ${groupName}? You can join it again later.`))return;
 btn.disabled=true;
 try{
  const result=await rpc('bw_leave_group',{p_user_id:uid(),p_group_id:groupId});
  const r=Array.isArray(result)?result[0]:result;
  if(!r?.ok)throw new Error(r?.message||'Could not leave group');
  await loadGroups();
  await loadGroupHappenings();
  renderGroupManager();
  renderOnboardingGroups();
  renderPeople();
 }catch(e){btn.disabled=false;alert('Could not leave the group. '+(e.message||e))}
}
async function createGroupInviteLink(groupId,groupName,isPrivate,pin,btn){
 if(!groupId)return;
 const base=window.location.href.split('#')[0].split('?')[0];
 const params=new URLSearchParams();
 params.set('group_invite',groupId);
 if(groupName)params.set('group_name',groupName);
 if(isPrivate&&pin)params.set('group_pin',pin);
 const url=base+'?'+params.toString();
 try{
  if(navigator.share){await navigator.share({title:`Join ${groupName}`,text:`Join my Brighton Weekend group, ${groupName}.`,url});return;}
  if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(url);alert('Invite link copied to your clipboard.');return;}
  window.prompt('Copy this group invite link:',url);
 }catch(e){
  if(e?.name==='AbortError')return;
  try{window.prompt('Copy this group invite link:',url)}catch(_){alert(url)}
 }
}
function renderGroupManager(){
 const el=$('groupManager'); if(!el)return;
 el.innerHTML=groups.length?groups.map(g=>`<div class="group-manager-row" data-group-id="${esc(g.id)}"><div><strong>${g.is_private?'🔒':'◌'} ${esc(g.name)}</strong><div class="group-meta">${g.member_count||1} members · ${g.is_private?'Private':'Open'}${g.join_pin?` · PIN <span class="pin-display">${esc(g.join_pin)}</span>`:''}</div></div><div class="row-actions"><button type="button" class="btn btn-chip" data-invite-group="${esc(g.id)}" data-invite-name="${esc(g.name)}" data-invite-private="${g.is_private?'1':'0'}" data-invite-pin="${esc(g.join_pin||'')}">Invite link</button><button type="button" class="btn btn-chip" data-leave-group="${esc(g.id)}" data-leave-name="${esc(g.name)}">Leave</button></div></div>`).join(''):'<div class="group-meta">No groups yet.</div>';
}

async function act(id,status){
 if(!name()){showWelcome('name');return}
 const mine=attendance.find(x=>x.event_id===id&&x.user_id===uid());
 const targetStatus=(mine&&mine.status===status)?null:status;
 try{
  const result=await rpc('bw_set_event_interest',{
   p_user_id:uid(),
   p_user_name:name(),
   p_event_id:id,
   p_status:targetStatus
  });
  if(!Array.isArray(result)) throw new Error('Unexpected response from Supabase.');
  await loadAttendance();
  const saved=attendance.find(x=>x.event_id===id&&x.user_id===uid());
  if(targetStatus===null){
   if(saved) throw new Error('Supabase did not remove the commitment.');
  }else if(!saved || saved.status!==targetStatus){
   throw new Error('Supabase did not save the commitment.');
  }
  await loadGroupHappenings();
  updateHappeningsBadge();
  renderAll();
 }catch(e){
  console.error('[Brighton Weekend] commitment save failed',e);
  alert('Could not save that yet. '+(e.message||e));
 }
}
function commitmentButtons(e,mine){
 const b=(status,cls,icon,label)=>`<button type="button" class="commit-btn ${cls}${mine?.status===status?' selected':''}" data-act="${esc(status)}" data-event-id="${esc(e.id)}" aria-pressed="${mine?.status===status}"><span class="commit-icon" aria-hidden="true">${icon}</span><span>${label}</span></button>`;
 return `<div class="commitment">${b('not_interested','no','×','Not for me')}${b('interested','yes','♡','Interested')}${b('ticket_bought','bought','🎟','Going')}</div>`;
}
function timeRange(e){return e.time?esc(e.time)+(e.finish_time?'–'+esc(e.finish_time):''):''}
function ticketLink(e){const u=safeUrl(e.ticket_url);return u?`<a class="ticket" href="${esc(u)}" target="_blank" rel="noopener">Tickets ↗</a>`:''}
function eventCard(e,{showDate=false}={}){
 const mine=attendance.find(x=>x.event_id===e.id&&x.user_id===uid());
 const a=uniqueGroupPeopleCount(e.id,'interested'), t=uniqueGroupPeopleCount(e.id,'ticket_bought');
 const d=showDate?parseEventDate(e.date):null;
 const when=[esc(e.venue_display||e.venue),timeRange(e)].filter(Boolean).join(' · ');
 return `<article class="card">${d?`<div class="card-date">${esc(d.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'}))}</div>`:''}<div class="top"><div><div class="title">${esc(e.title)}${e.is_custom?` <span class="added-by">added by ${esc(e.created_by_name||'community')}</span>`:''}</div><div class="meta">${when}</div></div>${e.status==='SOLD OUT'?'<span class="badge sold">Sold out</span>':''}</div>
 ${e.price?`<div class="price">${esc(e.price)}</div>`:''}
 <div class="people"><span class="social-chip"><i class="social-icon heart">♡</i>${a} interested</span><span class="social-chip"><i class="social-icon ticket">🎟</i>${t} going</span></div>
 ${commitmentButtons(e,mine)}
 <div class="actions">${ticketLink(e)}</div></article>`;
}
function render(){
 const end=new Date(weekStart);end.setDate(end.getDate()+6);
 $('week').textContent=weekStart.toLocaleDateString('en-GB',{day:'numeric',month:'short'})+' – '+end.toLocaleDateString('en-GB',{day:'numeric',month:'short'});
 const days=weekDays();
 if(!days.length){$('discover').innerHTML='<div class="empty">None of your chosen days are left this week. Tap › for next week, or change your days in Settings.</div>';return}
 $('discover').innerHTML=days.map(day=>{
  const list=events.filter(e=>e.date===day.key&&venueVisible(e)&&!isComedy(e));
  return dayHeading(day)+(list.length?list.map(e=>eventCard(e)).join(''):'<div class="empty">No events at your selected venues.</div>');
 }).join('');
}
function isComedy(e){
 const hay=[e.category,e.type,e.genre,e.tags,e.title,e.description].filter(Boolean).join(' ').toLowerCase();
 return /\b(comedy|comedian|stand.?up|standup|improv|improvisation|sketch|open mic comedy)\b/.test(hay);
}
function renderComedy(){
 const days=weekDays();
 const html=days.map(day=>{
  const list=events.filter(e=>e.date===day.key&&isComedy(e)&&venueVisible(e));
  return list.length?dayHeading(day)+list.map(e=>eventCard(e)).join(''):'';
 }).join('');
 $('comedyList').innerHTML=html||'<div class="empty">No comedy this week at your selected venues. Try another week or turn on more venues in Settings.</div>';
}
function renderPeople(){
 const byEvent=new Map();
 groupHappenings.forEach(x=>{if(!byEvent.has(x.event_id))byEvent.set(x.event_id,[]);byEvent.get(x.event_id).push(x)});
 const today=todayKey();
 const active=events.filter(e=>byEvent.has(e.id)&&e.date>=today).sort((a,b)=>(a.date+(a.time||'')).localeCompare(b.date+(b.time||'')));
 if(!groups.length){$('peopleList').innerHTML='<div class="empty">Join or create a group to see what your people are planning.</div>';return}
 const memberGroups=new Map();
 groupMembers.forEach(m=>{if(!memberGroups.has(m.group_id))memberGroups.set(m.group_id,{name:m.group_name,members:[]});memberGroups.get(m.group_id).members.push(m)});
 const roster=[...memberGroups.values()].map(g=>{
   const members=[...new Map(g.members.map(m=>[m.user_id,m])).values()].sort((a,b)=>(a.user_name||'').localeCompare(b.user_name||''));
   return `<div class="member-group"><div class="group-heading">${esc(g.name)} <span class="member-count">${members.length}</span></div><div class="people">${members.map(m=>`<span class="social-chip profile-chip"><i class="social-icon profile"><img src="${iconSrc(userIcon(m.user_id))}" alt=""></i>${esc(m.user_name)}</span>`).join('')}</div></div>`;
 }).join('');
 let html=`<section class="group-roster"><div class="section-head"><h3>People in your groups</h3><div class="note">Everyone who shares a group with you.</div></div>${roster}</section>`;
 if(!active.length){$('peopleList').innerHTML=html+'<div class="empty happenings-empty">No event activity yet. Mark an event as Interested or Going to get things started.</div>';return}
 html+='<div class="section-head happenings-events-head"><h3>What\'s happening</h3></div>';
 html+=active.map(e=>{
  const rows=byEvent.get(e.id)||[], mine=attendance.find(x=>x.event_id===e.id&&x.user_id===uid());
  const unique=new Map();
  rows.forEach(x=>{
    if(!x.user_id || !['interested','ticket_bought'].includes(x.status))return;
    const existing=unique.get(x.user_id);
    if(!existing || x.status==='ticket_bought') unique.set(x.user_id,x);
  });
  const goingCount=[...unique.values()].filter(x=>x.status==='ticket_bought').length;
  const interestedCount=[...unique.values()].filter(x=>x.status==='interested').length;
  const summary=[];
  if(goingCount)summary.push(`<span class="happening-summary-pill going">🎟 ${goingCount} friend${goingCount===1?'':'s'} going</span>`);
  if(interestedCount)summary.push(`<span class="happening-summary-pill interested">♡ ${interestedCount} interested</span>`);
  const byGroup=new Map();
  rows.forEach(x=>{if(!byGroup.has(x.group_id))byGroup.set(x.group_id,{name:x.group_name,rows:[]});byGroup.get(x.group_id).rows.push(x)});
  const sections=[...byGroup.values()].map(g=>{
   const peopleByUser=new Map();
   g.rows.filter(x=>['interested','ticket_bought'].includes(x.status)).forEach(x=>{
     const existing=peopleByUser.get(x.user_id);
     if(!existing || x.status==='ticket_bought')peopleByUser.set(x.user_id,x);
   });
   const people=[...peopleByUser.values()].sort((a,b)=>{
     if(a.status!==b.status)return a.status==='ticket_bought'?-1:1;
     return (a.user_name||'').localeCompare(b.user_name||'');
   });
   return `<div class="happening-group"><div class="group-heading">${esc(g.name)}</div><div class="happening-people">${people.map(x=>`<div class="happening-person"><i class="social-icon profile"><img src="${iconSrc(userIcon(x.user_id))}" alt=""></i><span class="happening-person-name">${esc(x.user_name)}</span><span class="happening-status ${x.status==='ticket_bought'?'going':'interested'}">${x.status==='ticket_bought'?'🎟 GOING':'♡ INTERESTED'}</span></div>`).join('')}</div></div>`;
  }).join('');
  return `<div class="people-card card"><div class="top"><div><h3>${esc(e.title)}${e.is_custom?` <span class="added-by">community added</span>`:''}</h3><div class="meta">${[esc(e.venue_display||e.venue),esc((parseEventDate(e.date)||new Date()).toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short'})),timeRange(e)].filter(Boolean).join(' · ')}</div></div>${e.status==='SOLD OUT'?'<span class="badge sold">SOLD OUT</span>':''}</div>${summary.length?`<div class="happening-summary">${summary.join('')}</div>`:''}${sections}${commitmentButtons(e,mine)}<div class="actions">${ticketLink(e)}</div></div>`;
 }).join('');
 $('peopleList').innerHTML=html;
}

function renderVenues(){
 $('venueList').innerHTML=VENUES.map(v=>`<label class="venue-row"><span>${esc(v)}</span><input type="checkbox" data-v="${esc(v)}" ${enabled.includes(v)?'checked':''}></label>`).join('');
 renderDayPreferences();
 document.querySelectorAll('[data-v]').forEach(x=>x.onchange=()=>{enabled=x.checked?[...new Set([...enabled,x.dataset.v])]:enabled.filter(v=>v!==x.dataset.v);localStorage.setItem('bw_venues',JSON.stringify(enabled));renderAll()});
 const comedy=$('selectComedyVenues'),all=$('selectAllVenues'),none=$('unselectAllVenues');
 if(comedy)comedy.onclick=()=>{enabled=[...new Set([...enabled,...COMEDY_VENUES])];localStorage.setItem('bw_venues',JSON.stringify(enabled));renderVenues();renderAll()};
 if(all)all.onclick=()=>{enabled=VENUES.slice();localStorage.setItem('bw_venues',JSON.stringify(enabled));renderVenues();renderAll()};
 if(none)none.onclick=()=>{enabled=[];localStorage.setItem('bw_venues',JSON.stringify(enabled));renderVenues();renderAll()};
}
function renderDayPreferences(){
 const grid=$('dayGrid');if(!grid)return;const s=selectedDays();
 grid.innerHTML=DAY_NAMES.map((d,i)=>`<label class="day-choice"><input type="checkbox" data-day="${i}" ${s.has(i)?'checked':''}><span>${d}</span></label>`).join('');
 grid.querySelectorAll('[data-day]').forEach(c=>c.onchange=()=>{const vals=[...grid.querySelectorAll('[data-day]:checked')].map(x=>Number(x.dataset.day));localStorage.setItem(DAYS_KEY,JSON.stringify(vals.length?vals:[0,1,2,3,4,5,6]));if(!vals.length)renderDayPreferences();renderAll()});
}
function debugData(){
 const ids=new Set(), duplicates=[];
 for(const e of events){if(ids.has(e.id))duplicates.push(e.id);ids.add(e.id)}
 const bad=events.filter(e=>!e.id||!parseEventDate(e.date)||!e.venue||!e.title);
 console.info('[Brighton Weekend] diagnostics',{events:events.length,duplicateIds:duplicates.length,invalidEvents:bad.length,venues:[...new Set(events.map(e=>e.venue))].length});
 if(duplicates.length)console.warn('[Brighton Weekend] duplicate event IDs',duplicates);
 if(bad.length)console.warn('[Brighton Weekend] invalid events',bad);
}

async function refresh(){
 try{
  const response=await fetch('events.json?refresh='+Date.now(),{cache:'no-store'});
  if(!response.ok)throw new Error(`Events feed returned ${response.status}`);
  const j=await response.json();
  const incoming=Array.isArray(j.events)?j.events:[];
  const seen=new Set(), cleaned=[];
  for(const e of incoming){
   if(!e||!e.id||seen.has(e.id))continue;
   seen.add(e.id);
   if(!parseEventDate(e.date))continue;
   cleaned.push(e);
  }
  events=mergeEvents(cleaned);
  $('subtitle').textContent=`${events.length} events · updated ${j.updated||''}`;
  debugData();
  renderAll();
  return {ok:true,count:events.length};
 }catch(e){
  console.warn('Events refresh failed',e);
  $('subtitle').textContent='Could not refresh events';
  return {ok:false,error:e};
 }
}

// ---- Search ----
let searchMode='venue';const searchVenues=new Set();
function populateSearchVenues(){
 const list=$('searchVenueList');if(!list)return;
 const q=($('searchVenueFilter').value||'').trim().toLowerCase();
 const names=[...new Set(events.map(e=>String(e.venue_display||e.venue||'').trim()).filter(Boolean))].sort();
 list.innerHTML=names.filter(v=>!q||v.toLowerCase().includes(q)).map(v=>`<label class="choice"><input type="checkbox" value="${esc(v)}" ${searchVenues.has(v)?'checked':''}><span>${esc(v)}</span></label>`).join('')||'<div class="empty">No venues match.</div>';
 list.querySelectorAll('input').forEach(i=>i.onchange=()=>{i.checked?searchVenues.add(i.value):searchVenues.delete(i.value);renderSearch()});
}
function setSearchMode(mode){
 searchMode=mode;
 document.querySelectorAll('[data-search-mode]').forEach(b=>{const on=b.dataset.searchMode===mode;b.classList.toggle('active',on);b.setAttribute('aria-pressed',on)});
 $('searchVenueMode').classList.toggle('hidden',mode!=='venue');$('searchArtistMode').classList.toggle('hidden',mode!=='artist');
 renderSearch();
}
function renderSearch(){
 const box=$('searchResults');if(!box)return;
 let out=[];
 if(searchMode==='artist'){
  const q=$('searchArtist').value.trim().toLowerCase();
  if(q)out=events.filter(e=>[e.title,e.description,e.artist].filter(Boolean).join(' ').toLowerCase().includes(q));
 }else{
  const from=$('searchFrom').value,to=$('searchTo').value;
  if(from&&to&&searchVenues.size)out=events.filter(e=>e.date>=from&&e.date<=to&&searchVenues.has(String(e.venue_display||e.venue||'').trim()));
 }
 const today=todayKey();out=out.filter(e=>e.date>=today);
 out.sort((a,b)=>(a.date+(a.time||'')).localeCompare(b.date+(b.time||'')));
 $('searchCount').textContent=out.length+' event'+(out.length===1?'':'s');
 box.innerHTML=out.length?out.slice(0,200).map(e=>eventCard(e,{showDate:true})).join(''):`<div class="empty">${searchMode==='artist'?'Type an artist or show name to search every date.':'Choose a date range and at least one venue.'}</div>`;
}
function setupSearch(){
 document.querySelectorAll('[data-search-mode]').forEach(b=>b.onclick=()=>setSearchMode(b.dataset.searchMode));
 ['searchFrom','searchTo'].forEach(id=>$(id).onchange=renderSearch);
 $('searchArtist').oninput=renderSearch;$('searchVenueFilter').oninput=populateSearchVenues;
 $('searchClear').onclick=()=>{searchVenues.clear();['searchFrom','searchTo','searchVenueFilter','searchArtist'].forEach(id=>$(id).value='');populateSearchVenues();setSearchMode('venue')};
}
setupSearch();

let deferredInstallPrompt=null;
function setupInstallButton(){const btn=$('installApp'),hint=$('installHint');if(!btn)return;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstallPrompt=e;});
window.addEventListener('appinstalled',()=>{deferredInstallPrompt=null;btn.classList.add('hidden');hint.textContent='Brighton Weekend is installed on your home screen.'});
btn.onclick=async()=>{if(deferredInstallPrompt){deferredInstallPrompt.prompt();await deferredInstallPrompt.userChoice;deferredInstallPrompt=null;return;}
const isiOS=/iPad|iPhone|iPod/.test(navigator.userAgent)&&!window.MSStream;
if(isiOS)alert('To add Brighton Weekend: use Safari, tap Share, choose “Add to Home Screen”, then tap Add. The Brighton Weekend icon will be used.');else alert('To add Brighton Weekend: open this site in Chrome, tap the three-dot menu, then choose “Install app” or “Add to Home screen”.');};
if(window.matchMedia('(display-mode: standalone)').matches||navigator.standalone){btn.classList.add('hidden');hint.textContent='Brighton Weekend is already installed.';}}
setupInstallButton();

$('googleSignInBtn').addEventListener('click',async()=>{const btn=$('googleSignInBtn'),msg=$('authMessage');try{btn.disabled=true;msg.textContent='Opening Google…';await signInWithGoogle();}catch(err){msg.textContent='Could not start Google sign-in. '+(err.message||err);btn.disabled=false}});
$('magicLinkForm').addEventListener('submit',async e=>{e.preventDefault();const btn=$('magicLinkBtn'),input=$('magicLinkEmail'),msg=$('authMessage');try{btn.disabled=true;input.disabled=true;msg.className='group-meta';msg.textContent='Sending your sign-in link…';await signInWithMagicLink(input.value);msg.className='group-meta auth-success';msg.textContent='Check your email — your sign-in link is on its way.';}catch(err){msg.className='group-meta auth-error';msg.textContent='Could not send the sign-in link. '+(err.message||err);btn.disabled=false;input.disabled=false;}});
$('nameForm').addEventListener('submit',async e=>{e.preventDefault();const n=$('nameInput').value.trim();if(!n)return;try{await saveProfile(n);await openGroupStep()}catch(err){alert('Could not save your profile. '+(err.message||err))}});
$('signOut').onclick=async()=>{await supabase.auth.signOut();authUser=null;authSession=null;profileName='';groups=[];groupMembers=[];attendance=[];groupHappenings=[];profileIconsByUser={};profileIcon='';localStorage.removeItem('bw_name');$('accountEmail').textContent='';renderAll();showWelcome('auth')};
$('partyOnBtn').onclick=finishWelcome;
$('showCreateGroup').onclick=()=>{hide('joinGroupPanel');$('createGroupPanel').classList.toggle('hidden')};
$('showJoinGroup').onclick=async()=>{hide('createGroupPanel');$('joinGroupPanel').classList.toggle('hidden');if(!$('joinGroupPanel').classList.contains('hidden'))await loadPublicGroups()};
$('newGroupPrivacy').onchange=()=>{$('pinNote').textContent=$('newGroupPrivacy').value==='private'?'A random 3 digit PIN will be created and shown to you.':'Anyone using Brighton Weekend can find and join this group.'};
$('createGroupBtn').onclick=createGroup;
$('joinPublicBtn').onclick=()=>{const id=$('publicGroupSelect').value;if(!id)return alert('Choose a group first.');joinGroup(id)};
$('joinPrivateBtn').onclick=()=>{const n=$('privateGroupName').value.trim(),p=$('privateGroupPin').value.trim();if(!n||!/^\d{3}$/.test(p))return alert('Enter the exact group name and a 3 digit PIN.');joinGroup(null,p,n)};
$('prev').onclick=()=>{weekStart.setDate(weekStart.getDate()-7);renderAll()};
$('next').onclick=()=>{weekStart.setDate(weekStart.getDate()+7);renderAll()};
$('today').onclick=()=>{weekStart=getMonday();renderAll()};
$('refresh').onclick=async()=>{
 const btn=$('refresh');btn.disabled=true;
 try{await loadCustomEvents();await refresh();await loadAttendance();await loadGroups();await loadGroupHappenings();renderAll();}
 finally{btn.disabled=false;}
};
$('changeName').onclick=()=>showWelcome('name');
$('manageGroups').onclick=()=>showWelcome('groups');
document.addEventListener('click',e=>{const b=e.target.closest('[data-leave-group]');if(!b)return;leaveGroup(b.dataset.leaveGroup,b.dataset.leaveName,b)});document.addEventListener('click',e=>{const b=e.target.closest('[data-invite-group]');if(!b)return;createGroupInviteLink(b.dataset.inviteGroup,b.dataset.inviteName,b.dataset.invitePrivate==='1',b.dataset.invitePin,b)});
$('customVenue').innerHTML='<option value="">Choose a venue…</option>'+VENUES.map(v=>`<option>${esc(v)}</option>`).join('');
$('customVenue').onchange=toggleOtherVenue;
$('toggleCustomEvent').onclick=()=>{const panel=$('customEventPanel');const open=panel.classList.toggle('collapsed')===false;$('toggleCustomEvent').textContent=open?'− Hide form':'＋ Add event';if(open) setTimeout(()=>$('customTitle').focus(),50)};
$('addCustomEventBtn').onclick=addCustomEvent;
const TABS=['discover','comedyTab','searchTab','peopleTab','venuesTab'];
document.querySelectorAll('.nav button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.nav button').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-current',x===b?'page':'false')});
 TABS.forEach(id=>$(id).classList.toggle('hidden',id!==b.dataset.tab));
 document.querySelector('header .controls').classList.toggle('hidden',['searchTab','venuesTab','peopleTab'].includes(b.dataset.tab));
 window.scrollTo(0,0);
 if(b.dataset.tab==='comedyTab')renderComedy();
 if(b.dataset.tab==='searchTab'){populateSearchVenues();renderSearch()}
 if(b.dataset.tab==='peopleTab'){renderPeople();markHappeningsSeen();updateHappeningsBadge()}
 if(b.dataset.tab==='venuesTab'){renderVenues();renderGroupManager()}
});
// Commitment buttons are rendered in several lists; one delegated handler serves them all.
document.addEventListener('click',e=>{const b=e.target.closest('[data-act]');if(!b)return;act(b.dataset.eventId,b.dataset.act)});
async function loadUserData(){
 if(!authUser)return;
 await Promise.all([loadAttendance(),loadCustomEvents()]);
 events=mergeEvents(events.filter(e=>!e.is_custom));
 await loadGroupHappenings(); await loadProfileIcons();
 renderProfileIconSettings(); renderAll(); renderGroupManager();
}
(async()=>{
 renderVenues(); renderAll();
 const eventsLoaded=refresh();
 try{await initAuth();}catch(e){console.error('Auth init failed',e);showWelcome('auth')}
 await eventsLoaded;
 await loadUserData();
})();
})();
