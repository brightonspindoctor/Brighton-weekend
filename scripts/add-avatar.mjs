import fs from 'node:fs';

const args = Object.fromEntries(process.argv.slice(2).map((arg) => {
  const [key, ...rest] = arg.replace(/^--/, '').split('=');
  return [key, rest.join('=')];
}));

const id = args.id?.trim();
const label = args.label?.trim();
const file = args.file?.trim();

if (!id || !label || !file) {
  throw new Error('Usage: node scripts/add-avatar.mjs --id=red-fox --label="Red Fox" --file=red-fox.png');
}
if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) throw new Error(`Invalid avatar id: ${id}`);
if (!/^[A-Za-z0-9._-]+$/.test(file)) throw new Error(`Invalid avatar filename: ${file}`);
if (!fs.existsSync(`profile-icons/${file}`)) throw new Error(`Missing asset: profile-icons/${file}`);
if (id === 'bee' || id === 'bumblebee') throw new Error('Legacy bee avatars are not allowed');

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
console.log(`Registered avatar ${id} (${label}) -> profile-icons/${file}`);
