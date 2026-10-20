import fs from 'node:fs';
import path from 'node:path';

const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const rootMatch = varsCss.match(/:root\s*\{([\s\S]*?)\}/);
const body = rootMatch ? rootMatch[1] : varsCss;
const defs = {};
for (const m of body.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) defs[m[1].trim()] = m[2].trim();

const themeDefs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css','src/assets/styles/base/base.css','src/assets/styles/base/utilities.css']) {
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) themeDefs.add(m[1]);
}

// remaining consumption details per var per file
const allFiles = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js)$/.test(e.name)) allFiles.push(p); } })('src');

const detail = {};
for (const f of allFiles) {
  if (f.endsWith('variables.css') || f.endsWith('main.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const v of Object.keys(defs)) {
    if (themeDefs.has(v)) continue;
    const re = new RegExp('var\\(\\s*'+v.replace(/[-]/g,'\\-')+'(?:[,)])','g');
    const n = (t.match(re)||[]).length;
    if (n>0) {
      detail[v] = detail[v]||[];
      detail[v].push(`${n}x ${f}`);
    }
  }
}
for (const [v, locs] of Object.entries(detail).sort((a,b)=>b[1].length-a[1].length)) {
  console.log(`\n${v}  def="${defs[v]}"`);
  for (const l of locs) console.log(`   ${l}`);
}
