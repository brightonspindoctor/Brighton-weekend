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
  for (const m of mapMatch[1].matchAll(/'([^']+)':'([^']+)'/g)) sourceMap[m[1]] = m[2];
}

function sourceFor(icon) {
  const explicit = sourceMap[icon];
  const candidates = [
    explicit,
    icon + '.png',
    icon + '.jpg',
    icon + '.jpeg',
    icon + '.webp',
    icon + '.svg'
  ].filter(Boolean);
  for (const c of candidates) {
    if (fs.existsSync(path.join(dir, c))) return c;
  }
  throw new Error(`No source artwork found for ${icon}`);
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

const NAVY = '#101C2C';
const TEAL = '#35A7A0';

for (const icon of icons) {
  const srcName = sourceFor(icon);
  const src = path.join(dir, srcName);
  const dest = path.join(outDir, icon + '.png');

  const artwork = await sharp(src)
    .resize(104, 104, { fit: 'cover', position: 'centre' })
    .png()
    .toBuffer();

  const maskSvg = Buffer.from(
    '<svg width="104" height="104" xmlns="http://www.w3.org/2000/svg"><circle cx="52" cy="52" r="52" fill="white"/></svg>'
  );

  const output = await sharp({
    create: { width: 128, height: 128, channels: 4, background: NAVY }
  })
    .composite([
      {
        input: Buffer.from(
          '<svg width="128" height="128" xmlns="http://www.w3.org/2000/svg">' +
          '<circle cx="64" cy="64" r="62" fill="' + TEAL + '"/>' +
          '<circle cx="64" cy="64" r="58" fill="' + NAVY + '"/>' +
          '</svg>'
        )
      },
      { input: artwork, left: 12, top: 12, blend: 'over', mask: undefined }
    ])
    .png()
    .toBuffer();

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

const standardizedMap = Object.fromEntries(icons.map(icon => [icon, `standardized/${icon}.png`]));
const replacement = 'const PROFILE_ICON_FILES=' + JSON.stringify(standardizedMap) + ';';
const updatedIndex = index.replace(/const PROFILE_ICON_FILES=\{.*?\};/s, replacement);
if (updatedIndex === index) throw new Error('PROFILE_ICON_FILES replacement failed');
fs.writeFileSync(indexPath, updatedIndex);

const manifest = {};
for (const icon of icons) {
  const file = path.join(outDir, icon + '.png');
  manifest[icon] = {
    label: icon.replace(/(^|-)([a-z])/g, (_, p, c) => (p ? ' ' : '') + c.toUpperCase()),
    file: 'standardized/' + icon + '.png',
    sha256: sha256(file)
  };
}
fs.writeFileSync(path.join(dir, 'avatar-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');

console.log(`Standardised ${icons.length} avatars to 128x128 PNG with navy/teal circular framing.`);
