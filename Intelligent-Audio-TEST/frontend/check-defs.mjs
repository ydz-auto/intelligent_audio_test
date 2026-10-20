import fs from 'node:fs';
import path from 'node:path';

// Exact global definitions: theme.css, theme-presets.css, base/*, plus any :root in other css that stays
const globalDefs = new Set();
const globalSrcs = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.css$/.test(e.name)) globalSrcs.push(p); } })('src');
// Definitions that remain after deletion: theme files + base + any css loaded via index chain
const remainingCss = ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css','src/assets/styles/base/index.css','src/assets/styles/base/reset.css','src/assets/styles/base/base.css','src/assets/styles/base/utilities.css'];
for (const f of remainingCss) {
  if (!fs.existsSync(f)) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) globalDefs.add(m[1]);
}
console.log('remaining global defs count:', globalDefs.size);
['--sidebar-width','--header-height','--footer-height','--page-margin','--content-min-width','--white-color','--border-width','--primary-gradient','--card-border','--btn-secondary-bg','--danger-required','--font-mono','--font-family-mono','--danger-dark','--font-size-2xl','--font-size-3xl','--spacing-2xl','--color-emerald-300'].forEach(v=>console.log(v, globalDefs.has(v)?'DEFINED':'MISSING'));
