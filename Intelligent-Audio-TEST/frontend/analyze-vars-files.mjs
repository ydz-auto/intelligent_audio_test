import fs from 'node:fs';
import path from 'node:path';

// variables.css definitions
const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const varDefs = [];
for (const m of varsCss.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) varDefs.push(m[1]);

// theme files definitions
const defs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css','src/assets/styles/base/base.css','src/assets/styles/base/utilities.css']) {
  try { const t = fs.readFileSync(f,'utf8'); for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) defs.add(m[1]); } catch(e){}
}

// all source files
const all = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js|html)$/.test(e.name)) all.push(p); } })('src');

// per-file consumption of MISSING vars
const fileConsumers = {};
for (const f of all) {
  if (f.endsWith('main.css') || f.endsWith('variables.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  const usedVars = new Set();
  for (const v of varDefs) {
    if (defs.has(v)) continue; // only MISSING ones
    const escaped = v.replace(/[-]/g, '\\-');
    const re = new RegExp('var\\(\\s*' + escaped + '(?:[,)\\s])', 'g');
    const n = (t.match(re)||[]).length;
    if (n>0) { usedVars.add(v); }
  }
  if (usedVars.size>0) {
    fileConsumers[f] = { count: usedVars.size, vars: [...usedVars] };
  }
}

console.log('=== 文件消费「theme 未定义旧别名」的数量与清单 ===');
const entries = Object.entries(fileConsumers).sort((a,b)=>b[1].count-a[1].count);
for (const [f,{count,vars}] of entries) {
  console.log(`${String(count).padStart(3)}  ${f}`);
  if (count<=4) console.log(`        vars: ${vars.join(', ')}`);
}
console.log('\ntotal files with missing-var consumers:', entries.length);
