import fs from 'node:fs';
import crypto from 'node:crypto';

const source = fs.readFileSync('index.html', 'utf8');
const iconsMatch = source.match(/PROFILE_ICONS\s*=\s*\[([^\]]+)\]/s);
if (!iconsMatch) throw new Error('PROFILE_ICONS registry not found');
const names = [...iconsMatch[1].matchAll(/['\"]([^'\"]+)['\"]/g)].map((m) => m[1]);

const filesMatch = source.match(/PROFILE_ICON_FILES\s*=\s*\{([^}]*)\}/s);
const files = {};
if (filesMatch) {
  for (const m of filesMatch[1].matchAll(/['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]/g)) files[m[1]] = m[2];
}

const manifestPath = 'profile-icons/avatar-manifest.json';
const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {};

for (const id of names) {
  const file = files[id] || `${id}.png`;
  const assetPath = `profile-icons/${file}`;
  if (!fs.existsSync(assetPath)) throw new Error(`Missing avatar asset: ${id} -> ${file}`);

  // Existing legacy avatars may be SVGs. New selected-artwork entries in the
  // manifest must be raster and must retain the exact selected file bytes.
  if (manifest[id]) {
    const ext = file.slice(file.lastIndexOf('.')).toLowerCase();
    if (!['.png', '.jpg', '.jpeg', '.webp'].includes(ext)) {
      throw new Error(`Avatar ${id} uses unsupported/non-raster selected artwork: ${file}`);
    }
    if (manifest[id].file !== file) throw new Error(`Avatar manifest mismatch: ${id} -> ${file}`);
    const actualSha256 = crypto.createHash('sha256').update(fs.readFileSync(assetPath)).digest('hex');
    if (manifest[id].sha256 !== actualSha256) {
      throw new Error(`Avatar artwork changed after selection: ${id} -> ${file}`);
    }
  }
}

if (names.includes('bee') || names.includes('bumblebee')) throw new Error('Legacy bee avatar still registered');
console.log(`Validated ${names.length} avatar assets; selected-artwork fingerprints checked for ${Object.keys(manifest).length} registered raster avatars.`);
