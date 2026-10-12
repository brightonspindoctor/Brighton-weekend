// Checks every avatar in PROFILE_ICONS (index.html): the app shows
// profile-icons/standardized/<id>.png, and both it and the selected artwork
// must still match the fingerprints recorded in avatar-manifest.json.
import fs from 'node:fs';
import crypto from 'node:crypto';

const source = fs.readFileSync('index.html', 'utf8');
const iconsMatch = source.match(/PROFILE_ICONS\s*=\s*\[([^\]]+)\]/s);
if (!iconsMatch) throw new Error('PROFILE_ICONS registry not found');
const names = [...iconsMatch[1].matchAll(/['"]([^'"]+)['"]/g)].map((m) => m[1]);

const manifestPath = 'profile-icons/avatar-manifest.json';
const manifest = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : {};
const sha = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

for (const id of names) {
  const file = `standardized/${id}.png`;
  const assetPath = `profile-icons/${file}`;
  if (!fs.existsSync(assetPath)) throw new Error(`Missing avatar: ${id} -> ${assetPath} (run scripts/standardize-avatars.mjs)`);
  const entry = manifest[id];
  if (!entry) throw new Error(`Avatar ${id} is not in ${manifestPath}`);
  if (entry.file !== file) throw new Error(`Avatar manifest mismatch: ${id} -> ${entry.file}, expected ${file}`);
  if (entry.sha256 !== sha(assetPath)) throw new Error(`Avatar ${id}: ${assetPath} changed without the manifest being updated`);
  // The selected artwork must still be the exact file that was chosen, and raster.
  const art = `profile-icons/${entry.source || ''}`;
  if (!entry.source || !fs.existsSync(art)) throw new Error(`Avatar ${id}: selected artwork ${art} is missing`);
  if (!/\.(png|jpe?g|webp)$/i.test(entry.source)) throw new Error(`Avatar ${id}: selected artwork must be PNG, JPG or WebP, not ${entry.source}`);
  if (entry.source_sha256 !== sha(art)) throw new Error(`Avatar ${id}: selected artwork ${art} changed after selection`);
}

if (names.includes('bee') || names.includes('bumblebee')) throw new Error('Legacy bee avatar still registered');
console.log(`Validated ${names.length} avatars: standardised files and selected artwork fingerprints all match.`);
