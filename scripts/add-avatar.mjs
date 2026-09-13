import fs from 'node:fs';
import crypto from 'node:crypto';

const args = Object.fromEntries(process.argv.slice(2).map((arg) => {
  const [key, ...rest] = arg.replace(/^--/, '').split('=');
  return [key, rest.join('=')];
}));

const id = args.id?.trim();
const label = args.label?.trim();
const file = args.file?.trim();

if (!id || !label || !file) {
  throw new Error('Usage: node scripts/add-avatar.mjs --id=red-fox --label="Red Fox" --file=red-fox.jpg');
}
if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) throw new Error(`Invalid avatar id: ${id}`);
if (!/^[A-Za-z0-9._-]+$/.test(file)) throw new Error(`Invalid avatar filename: ${file}`);
if (id === 'bee' || id === 'bumblebee') throw new Error('Legacy bee avatars are not allowed');

// Avatar creation must use the selected raster artwork itself. Do not substitute
// a recreated/vector placeholder after an image has been selected.
const ext = file.slice(file.lastIndexOf('.')).toLowerCase();
if (!['.png', '.jpg', '.jpeg', '.webp'].includes(ext)) {
  throw new Error(`Avatar assets must be raster images (.png, .jpg, .jpeg or .webp), not ${ext || 'an extensionless file'}`);
}

const assetPath = `profile-icons/${file}`;
if (!fs.existsSync(assetPath)) throw new Error(`Missing selected avatar asset: ${assetPath}`);
const bytes = fs.readFileSync(assetPath);

const signatures = [
  ['.png', bytes.length >= 8 && bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))],
  ['.jpg', bytes.length >= 3 && bytes.subarray(0, 3).equals(Buffer.from([255,216,255]))],
  ['.jpeg', bytes.length >= 3 && bytes.subarray(0, 3).equals(Buffer.from([255,216,255]))],
  ['.webp', bytes.length >= 12 && bytes.subarray(0, 4).toString() === 'RIFF' && bytes.subarray(8, 12).toString() === 'WEBP'],
];
if (!signatures.find(([kind, ok]) => kind === ext && ok)) {
  throw new Error(`Selected avatar asset does not match its ${ext} file type: ${assetPath}`);
}

const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');

const path = 'index.html';
let source = fs.readFileSync(path, 'utf8');

const iconsMatch = source.match(/const PROFILE_ICONS\s*=\s*\[([^\]]*)\]/s);
if (!iconsMatch) throw new Error('PROFILE_ICONS registry not found');
if (new RegExp(`['\"]${id}['\"]`).test(iconsMatch[1])) throw new Error(`Avatar already registered: ${id}`);

source = source.replace(/const PROFILE_ICONS\s*=\s*\[([^\]]*)\]/s, (full, body) => {
  const trimmed = body.trim();
  const next = trimmed ? `${trimmed},'${id}'` : `'${id}'`;
  return `const PROFILE_ICONS=[${next}]`;
});

const labelsMatch = source.match(/const PROFILE_LABELS\s*=\s*\{([^}]*)\}/s);
if (!labelsMatch) throw new Error('PROFILE_LABELS registry not found');
source = source.replace(/const PROFILE_LABELS\s*=\s*\{([^}]*)\}/s, (full, body) => {
  const trimmed = body.trim();
  const next = trimmed ? `${trimmed},'${id}':'${label.replaceAll("'", "\\'")}'` : `'${id}':'${label.replaceAll("'", "\\'")}'`;
  return `const PROFILE_LABELS={${next}}`;
});

const filesMatch = source.match(/const PROFILE_ICON_FILES\s*=\s*\{([^}]*)\}/s);
if (filesMatch) {
  source = source.replace(/const PROFILE_ICON_FILES\s*=\s*\{([^}]*)\}/s, (full, body) => {
    const trimmed = body.trim();
    const next = trimmed ? `${trimmed},'${id}':'${file}'` : `'${id}':'${file}'`;
    return `const PROFILE_ICON_FILES={${next}}`;
  });
}

fs.writeFileSync(path, source);

const manifestPath = 'profile-icons/avatar-manifest.json';
let manifest = {};
if (fs.existsSync(manifestPath)) manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
manifest[id] = { label, file, sha256 };
fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

console.log(`Registered avatar ${id} (${label}) -> ${assetPath}`);
console.log(`Selected artwork SHA-256: ${sha256}`);
