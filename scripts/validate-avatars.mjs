import fs from 'node:fs';

const source = fs.readFileSync('index.html', 'utf8');
const iconsMatch = source.match(/PROFILE_ICONS\s*=\s*\[([^\]]+)\]/s);
if (!iconsMatch) throw new Error('PROFILE_ICONS registry not found');
const names = [...iconsMatch[1].matchAll(/['\"]([^'\"]+)['\"]/g)].map((m) => m[1]);

const filesMatch = source.match(/PROFILE_ICON_FILES\s*=\s*\{([^}]*)\}/s);
const files = {};
if (filesMatch) {
  for (const m of filesMatch[1].matchAll(/['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]/g)) files[m[1]] = m[2];
}

for (const id of names) {
  const file = files[id] || `${id}.png`;
  if (!fs.existsSync(`profile-icons/${file}`)) throw new Error(`Missing avatar asset: ${id} -> ${file}`);
}

if (names.includes('bee') || names.includes('bumblebee')) throw new Error('Legacy bee avatar still registered');
console.log(`Validated ${names.length} avatar assets.`);
