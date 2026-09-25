// Builds profile-icons/standardized/<icon>.png from the source artwork.
//
// Every avatar comes out identical in format: 192x192 PNG, the artwork cut to
// a clean circle, transparent outside. No ring, rim or background square is
// painted in; the app draws the single outline in CSS (see DESIGN-SYSTEM.md).
//
// Sources can be PNG/JPG/WEBP, or an SVG wrapping an embedded image. Many
// sources already have a dark rim or a painted ring near the edge, so the
// circle is cut slightly inside the artwork (CROP) to remove it.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import sharp from 'sharp';

const root = process.cwd();
const dir = path.join(root, 'profile-icons');
const outDir = path.join(dir, 'standardized');
const SIZE = 192;
const CROP = 0.86; // fraction of the source's width kept inside the circle
fs.mkdirSync(outDir, { recursive: true });

// The icon list lives in the app code: inline in index.html (js/app.js in a split build).
const codeFile = ['index.html', 'js/app.js'].map(f => path.join(root, f))
  .find(f => fs.existsSync(f) && /const PROFILE_ICONS=\[/.test(fs.readFileSync(f, 'utf8')));
if (!codeFile) throw new Error('PROFILE_ICONS not found in index.html or js/app.js');
const code = fs.readFileSync(codeFile, 'utf8');
const icons = [...code.match(/const PROFILE_ICONS=\[(.*?)\];/s)[1].matchAll(/'([^']+)'/g)].map(m => m[1]);

function sourceFor(icon) {
  for (const ext of ['.png', '.jpg', '.jpeg', '.webp', '.svg']) {
    const f = icon + ext;
    if (fs.existsSync(path.join(dir, f))) return f;
  }
  throw new Error(`No source artwork found for ${icon}`);
}

function load(file) {
  const raw = fs.readFileSync(path.join(dir, file));
  if (file.endsWith('.svg')) {
    const m = raw.toString('utf8').match(/data:image\/(?:webp|png|jpeg);base64,([^"']+)/i);
    if (m) return sharp(Buffer.from(m[1].replace(/\s/g, ''), 'base64'), { failOn: 'none' });
  }
  return sharp(raw, { failOn: 'none' });
}

const mask = Buffer.from(`<svg width="${SIZE}" height="${SIZE}" xmlns="http://www.w3.org/2000/svg"><circle cx="${SIZE / 2}" cy="${SIZE / 2}" r="${SIZE / 2}" fill="#fff"/></svg>`);
const scaled = Math.round(SIZE / CROP);
const offset = Math.floor((scaled - SIZE) / 2);
const failures = [];

for (const icon of icons) {
  const src = sourceFor(icon);
  try {
    const art = await load(src)
      .resize(scaled, scaled, { fit: 'cover', position: 'centre' })
      .extract({ left: offset, top: offset, width: SIZE, height: SIZE })
      .ensureAlpha()
      .png()
      .toBuffer();
    const out = await sharp(art).composite([{ input: mask, blend: 'dest-in' }]).png({ compressionLevel: 9 }).toBuffer();
    fs.writeFileSync(path.join(outDir, icon + '.png'), out);
  } catch (err) {
    failures.push(`${icon} (${src}): ${err.message}`);
  }
}
if (failures.length) throw new Error('Could not read avatar artwork:\n' + failures.join('\n'));

// Point every icon at its standardised file.
const map = Object.fromEntries(icons.map(icon => [icon, 'standardized/' + icon + '.png']));
const updated = code.replace(/const PROFILE_ICON_FILES\s*=\s*\{.*?\};/s, 'const PROFILE_ICON_FILES=' + JSON.stringify(map) + ';');
fs.writeFileSync(codeFile, updated);

const labels = Object.fromEntries([...(code.match(/const PROFILE_LABELS=\{(.*?)\};/s)?.[1] || '').matchAll(/'([^']+)':'([^']+)'/g)].map(m => [m[1], m[2]]));
const manifest = {};
for (const icon of icons) {
  const file = path.join(outDir, icon + '.png');
  manifest[icon] = {
    label: labels[icon] || icon.replace(/(^|-)([a-z])/g, (_, p, c) => (p ? ' ' : '') + c.toUpperCase()),
    file: 'standardized/' + icon + '.png',
    sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
  };
}
fs.writeFileSync(path.join(dir, 'avatar-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Standardised ${icons.length} avatars to ${SIZE}px circular PNGs (updated ${path.relative(root, codeFile)}).`);
