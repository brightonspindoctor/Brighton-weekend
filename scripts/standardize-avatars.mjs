// Builds profile-icons/standardized/<icon>.png from the source artwork.
//
// Every avatar comes out identical in format: 192x192 PNG, the artwork cut to
// a clean circle, transparent outside. No ring, rim or background square is
// painted in; the app draws the single outline in CSS (see DESIGN-SYSTEM.md).
//
// Sources can be PNG/JPG/WEBP, or an SVG wrapping an embedded image. Many
// sources already have a dark rim or a painted ring near the edge, so the
// circle is cut slightly inside the artwork (CROP) to remove it. The artwork
// is then drawn at ZOOM of the circle's width with a soft edge, over a fill
// matching the artwork's own dark background, so avatars aren't cramped and no
// second ring appears.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import sharp from 'sharp';

const root = process.cwd();
const dir = path.join(root, 'profile-icons');
const outDir = path.join(dir, 'standardized');
const SIZE = 192;
const CROP = 0.86; // fraction of the source's width kept (removes painted rims)
const ZOOM = 0.88; // artwork diameter as a fraction of the avatar (smaller = more zoomed out)
const FEATHER = 0.14; // soft edge on the artwork, as a fraction of its radius
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

const circle = (d, feather = 0) => Buffer.from(`<svg width="${d}" height="${d}" xmlns="http://www.w3.org/2000/svg"><defs><radialGradient id="g"><stop offset="${1 - feather}" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs><circle cx="${d / 2}" cy="${d / 2}" r="${d / 2}" fill="${feather ? 'url(#g)' : '#fff'}"/></svg>`);
const mask = circle(SIZE);
const FALLBACK_BG = [11, 27, 38];

// The fill behind the artwork: the median of the dark pixels around the
// artwork's edge, so it matches that image's own background (not the subject).
async function backgroundOf(art) {
  const { data } = await sharp(art).raw().toBuffer({ resolveWithObject: true });
  const dark = [];
  const c = SIZE / 2, r = SIZE / 2 - 8;
  for (let a = 0; a < 360; a += 2) {
    const x = Math.round(c + r * Math.cos(a * Math.PI / 180)), y = Math.round(c + r * Math.sin(a * Math.PI / 180));
    const i = (y * SIZE + x) * 4;
    if (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2] < 55) dark.push([data[i], data[i + 1], data[i + 2]]);
  }
  const channel = k => dark.length > 20 ? dark.map(p => p[k]).sort((a, b) => a - b)[dark.length >> 1] : FALLBACK_BG[k];
  return { r: channel(0), g: channel(1), b: channel(2), alpha: 1 };
}
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
    const d = Math.round(SIZE * ZOOM), o = Math.floor((SIZE - d) / 2);
    const small = await sharp(art).resize(d, d).composite([{ input: circle(d, FEATHER), blend: 'dest-in' }]).png().toBuffer();
    const out = await sharp({ create: { width: SIZE, height: SIZE, channels: 4, background: await backgroundOf(art) } })
      .composite([{ input: small, left: o, top: o }, { input: mask, blend: 'dest-in' }])
      .png({ compressionLevel: 9 })
      .toBuffer();
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
