import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import sharp from 'sharp';

const root = process.cwd();
const dir = path.join(root, 'profile-icons');
const outDir = path.join(dir, 'standardized');
fs.mkdirSync(outDir, { recursive: true });

const indexPath = path.join(root, 'index.html');
const index = fs.readFileSync(indexPath, 'utf8');

const iconsMatch = index.match(/const PROFILE_ICONS=\[(.*?)\];/s);
if (!iconsMatch) throw new Error('PROFILE_ICONS not found');
const icons = [...iconsMatch[1].matchAll(/'([^']+)'/g)].map(m => m[1]);

const mapMatch = index.match(/const PROFILE_ICON_FILES=\{(.*?)\};/s);
const sourceMap = {};
if (mapMatch) {
  for (const m of mapMatch[1].matchAll(/[\"']([^\"']+)[\"']\s*:\s*[\"']([^\"']+)[\"']/g)) sourceMap[m[1]] = m[2];
}

function sourceFor(icon) {
  const explicit = sourceMap[icon];
  const candidates = [
    explicit && !explicit.startsWith('standardized/') ? explicit : null,
    icon + '.png',
    icon + '.jpg',
    icon + '.jpeg',
    icon + '.webp',
    icon + '.svg',
    explicit
  ].filter(Boolean);
  for (const c of candidates) {
    if (fs.existsSync(path.join(dir, c))) return c;
  }
  throw new Error(`No source artwork found for ${icon}`);
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

async function sourceImage(src) {
  const raw = fs.readFileSync(src);
  if (src.toLowerCase().endsWith('.svg')) {
    const text = raw.toString('utf8');
    const match = text.match(/data:image\/webp;base64,([^"']+)/i);
    if (match) return sharp(Buffer.from(match[1], 'base64'), { failOn: 'none' });
  }
  return sharp(raw, { failOn: 'none' });
}

const NAVY = '#101C2C';
const TEAL = '#35A7A0';

const sourceOnlyIcons = ['brown-bear','red-panda-bear','giant-panda-bear','forest-spirit','moon-hare','leviathan'];

for (const icon of icons) {
  const srcName = sourceFor(icon);
  const src = path.join(dir, srcName);
  const dest = path.join(outDir, icon + '.png');

  if (sourceOnlyIcons.includes(icon)) continue;

  const base = await sourceImage(src);
  const isBear = ['brown-bear', 'red-panda-bear', 'giant-panda-bear'].includes(icon);
  const artwork = isBear
    ? await base.resize(124, 124, { fit: 'cover', position: 'centre' }).extract({ left: 10, top: 10, width: 104, height: 104 }).png().toBuffer()
    : await base.resize(104, 104, { fit: 'cover', position: 'centre' }).png().toBuffer();

  const maskSvg = Buffer.from(
    '<svg width="104" height="104" xmlns="http://www.w3.org/2000/svg"><circle cx="52" cy="52" r="52" fill="white"/></svg>'
  );

  // Apply a circular alpha mask to the artwork layer by rebuilding the composite cleanly.
  const maskedArtwork = await sharp(artwork)
    .composite([{ input: maskSvg, blend: 'dest-in' }])
    .png()
    .toBuffer();

  const final = await sharp({
    create: { width: 128, height: 128, channels: 4, background: NAVY }
  })
    .composite([
      { input: Buffer.from('<svg width="128" height="128" xmlns="http://www.w3.org/2000/svg"><circle cx="64" cy="64" r="62" fill="' + TEAL + '"/><circle cx="64" cy="64" r="58" fill="' + NAVY + '"/></svg>') },
      { input: maskedArtwork, left: 12, top: 12 }
    ])
    .png()
    .toBuffer();

  fs.writeFileSync(dest, final);
}

const standardizedMap = Object.fromEntries(icons.map(icon => {
  const sourceOnly = sourceOnlyIcons.includes(icon);
  return [icon, sourceOnly ? (sourceMap[icon] || icon + '.webp') : 'standardized/' + icon + '.png'];
}));
const replacement = 'const PROFILE_ICON_FILES=' + JSON.stringify(standardizedMap) + ';';
const updatedIndex = index.replace(/const PROFILE_ICON_FILES=\{.*?\};/s, replacement);
if (updatedIndex === index) throw new Error('PROFILE_ICON_FILES replacement failed');
fs.writeFileSync(indexPath, updatedIndex);

const manifest = {};
for (const icon of icons) {
  const sourceOnly = sourceOnlyIcons.includes(icon);
  const file = sourceOnly ? path.join(dir, sourceMap[icon] || icon + '.webp') : path.join(outDir, icon + '.png');
  manifest[icon] = {
    label: icon.replace(/(^|-)([a-z])/g, (_, p, c) => (p ? ' ' : '') + c.toUpperCase()),
    file: sourceOnly ? (sourceMap[icon] || icon + '.webp') : 'standardized/' + icon + '.png',
    sha256: sha256(file)
  };
}
fs.writeFileSync(path.join(dir, 'avatar-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');

console.log(`Standardised ${icons.length} avatars to 128x128 PNG with navy/teal circular framing.`);
