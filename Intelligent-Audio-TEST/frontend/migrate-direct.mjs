import fs from 'node:fs';
import path from 'node:path';

// Direct aliases: old -> new (from variables.css :root)
const direct = {
  '--primary-color': '--primary',
  '--primary-light': '--accent',
  '--primary-dark': '--primary-hover',
  '--secondary-color': '--secondary',
  '--secondary-dark': '--secondary-deep',
  '--success-color': '--success',
  '--warning-color': '--warning',
  '--error-color': '--destructive',
  '--error-light': '--destructive-light',
  '--danger-color': '--destructive',
  '--danger-light': '--destructive-light',
  '--text-primary': '--foreground',
  '--text-secondary': '--muted-foreground',
  '--gray-color': '--gray',
  '--gray-light-color': '--gray-light',
  '--border-color': '--border',
  '--dark-color': '--foreground',
  '--background-primary': '--background',
  '--background-secondary': '--muted',
  '--background-tertiary': '--gray-light',
  '--border-radius-sm': '--radius-sm',
  '--border-radius-md': '--radius-md',
  '--border-radius-lg': '--radius-lg',
  '--border-radius-xl': '--radius-xl',
  '--border-radius-xxl': '--radius-xxl',
  '--border-radius-full': '--radius-full',
  '--card-radius': '--radius-card',
  '--card-shadow': '--shadow-md',
  '--card-shadow-hover': '--shadow-lg',
  '--btn-primary-bg': '--primary-gradient', // target is composite, handled separately
  '--btn-border-radius': '--radius-control',
  '--text-muted': '--muted-foreground',
  '--input-bg': '--background',
  '--disabled-bg': '--gray-light',
  '--background-hover': '--gray-light',
  '--btn-secondary-hover': '--secondary-light',
  '--border-color-light': '--border',
  '--pending-color': '--warning',
  '--pending-light': '--warning-light',
  '--pending-border': '--warning',
  '--in-progress-color': '--info',
  '--info-color': '--info',
  '--success-border': '--success',
  '--warning-border': '--warning',
  '--card-bg': '--card',
  '--bg-color': '--background',
  '--hover-bg': '--muted',
  '--badge-bg': '--muted',
  '--border-hover': '--border',
  '--table-header': '--muted',
};

const SRC = 'src';
const allFiles = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js|mjs)$/.test(e.name)) allFiles.push(p); } })(SRC);

// Skip these files entirely (source of truth / to be deleted)
const skip = new Set(['src/assets/styles/variables.css']);

let totalReplaced = 0;
const perFile = {};
for (const f of allFiles) {
  if (skip.has(f)) continue;
  const abs = path.resolve(f);
  let t = fs.readFileSync(f,'utf8');
  let orig = t;
  for (const [oldV, newV] of Object.entries(direct)) {
    // Only replace var(--old) or var(--old, fallback) — not definitions like "--old:" (unlikely but guard)
    const escaped = oldV.replace(/[-]/g,'\\-');
    const re = new RegExp('var\\(\\s*' + escaped + '(\\s*[,)])', 'g');
    let m;
    const before = t;
    t = t.replace(re, (match, tail) => `var(${newV}${tail}`);
    const replaced = (before.match(re)||[]).length;
    if (replaced > 0) totalReplaced += replaced;
  }
  if (t !== orig) {
    fs.writeFileSync(f, t, 'utf8');
    perFile[path.relative('.', f)] = (orig.length - t.length);
  }
}

console.log('total var() replaced:', totalReplaced);
console.log('files changed:', Object.keys(perFile).length);
