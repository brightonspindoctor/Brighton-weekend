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
// The label is written into index.html as a JavaScript string, so keep it to
// plain characters: no quotes, backslashes, braces or angle brackets.
if (!/^[A-Za-z0-9][A-Za-z0-9 &()\-]{0,39}$/.test(label)) throw new Error(`Invalid avatar label (letters, numbers, spaces, & ( ) - only, up to 40 characters): ${label}`);
if (id === 'bee' || id === 'bumblebee') throw new Error('Legacy bee avatars are not allowed');

// Avatar creation must use the selected raster artwork itself. Do not substitute
// a recreated/vector placeholder after an image has been selected.
const ext = file.slice(file.lastIndexOf('.')).toLowerCase();
if (!['.png', '.jpg', '.jpeg', '.webp'].includes(ext)) {
  throw new Error(`Avatar assets must be raster images (.png, .jpg, .jpeg or .webp), not ${ext || 'an extensionless file'}`);
}

const uploadedPath = `profile-icons/${file}`;
if (!fs.existsSync(uploadedPath)) throw new Error(`Missing selected avatar asset: ${uploadedPath}`);
const bytes = fs.readFileSync(uploadedPath);

const signatures = [
  ['.png', bytes.length >= 8 && bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))],
  ['.jpg', bytes.length >= 3 && bytes.subarray(0, 3).equals(Buffer.from([255,216,255]))],
  ['.jpeg', bytes.length >= 3 && bytes.subarray(0, 3).equals(Buffer.from([255,216,255]))],
  ['.webp', bytes.length >= 12 && bytes.subarray(0, 4).toString() === 'RIFF' && bytes.subarray(8, 12).toString() === 'WEBP'],
];
if (!signatures.find(([kind, ok]) => kind === ext && ok)) {
  throw new Error(`Selected avatar asset does not match its ${ext} file type: ${uploadedPath}`);
}

const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');

// The standardise step finds each avatar's artwork as profile-icons/<id>.<ext>,
// so the selected file is stored under that name. The bytes are copied
// unchanged (same fingerprint): the selected artwork is still the artwork.
const sourceFile = `${id}${ext === '.jpeg' ? '.jpg' : ext}`;
const assetPath = `profile-icons/${sourceFile}`;
for (const other of ['.png', '.jpg', '.jpeg', '.webp', '.svg']) {
  const clash = `profile-icons/${id}${other}`;
  if (clash !== assetPath && clash !== uploadedPath && fs.existsSync(clash)) throw new Error(`Another artwork file already uses this id: ${clash}`);
}
// Larger artwork crops cleanly; the app shows avatars at up to 192px.
const dims = (() => {
  if (ext === '.png' && bytes.length > 24) return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
  return null;
})();
if (dims && (dims[0] < 192 || dims[1] < 192)) throw new Error(`Artwork is ${dims[0]}x${dims[1]}; it needs to be at least 192x192 (ideally 512 or more, square)`);

const path = 'index.html';
let source = fs.readFileSync(path, 'utf8');

const iconsMatch = source.match(/const PROFILE_ICONS\s*=\s*\[([^\]]*)\]/s);
if (!iconsMatch) throw new Error('PROFILE_ICONS registry not found');
if (new RegExp(`['\"]${id}['\"]`).test(iconsMatch[1])) throw new Error(`Avatar already registered: ${id}`);

// All checks passed: store the selected file under the avatar's id.
if (uploadedPath !== assetPath) {
  if (fs.existsSync(assetPath)) throw new Error(`${assetPath} already exists`);
  fs.copyFileSync(uploadedPath, assetPath);
  fs.unlinkSync(uploadedPath);
}


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
    const next = trimmed ? `${trimmed},'${id}':'${sourceFile}'` : `'${id}':'${sourceFile}'`;
    return `const PROFILE_ICON_FILES={${next}}`;
  });
}

fs.writeFileSync(path, source);

const manifestPath = 'profile-icons/avatar-manifest.json';
let manifest = {};
if (fs.existsSync(manifestPath)) manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
// file/sha256 describe the file the app shows; the standardise step replaces
// them with the cropped circle and keeps source/source_sha256 as the record of
// the selected artwork.
manifest[id] = { label, source: sourceFile, source_sha256: sha256, file: sourceFile, sha256 };
fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

console.log(`Registered avatar ${id} (${label}) -> ${assetPath}`);
console.log('Next: node scripts/standardize-avatars.mjs && node scripts/validate-avatars.mjs');
console.log(`Selected artwork SHA-256: ${sha256}`);
