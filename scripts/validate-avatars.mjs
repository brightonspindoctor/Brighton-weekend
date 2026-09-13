import fs from 'node:fs';
const source=fs.readFileSync('index.html','utf8');
const match=source.match(/PROFILE_ICONS\s*=\s*\[([^\]]+)\]/s);
if(!match) throw new Error('PROFILE_ICONS registry not found');
const names=[...match[1].matchAll(/['\"]([^'\"]+)['\"]/g)].map(m=>m[1]);
const special={
  'brown-bear':'brown-bear.svg',
  'red-panda-bear':'red-panda-bear.svg',
  'giant-panda-bear':'giant-panda-bear.svg',
  'raccoon':'raccoon.jpg'
};
for(const id of names){
  const file=special[id]||`${id}.png`;
  if(!fs.existsSync(`profile-icons/${file}`)) throw new Error(`Missing avatar asset: ${id} -> ${file}`);
}
if(names.includes('bee')||names.includes('bumblebee')) throw new Error('Legacy bee avatar still registered');
console.log(`Validated ${names.length} avatar assets.`);
