import fs from 'node:fs';
import path from 'node:path';

// collect all css vars defined in theme files
const defs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css','src/assets/styles/base/base.css','src/assets/styles/base/utilities.css']) {
  try { const t = fs.readFileSync(f,'utf8'); for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) defs.add(m[1]); } catch(e){}
}
// variables.css definitions
const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const varDefs = new Set();
for (const m of varsCss.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) varDefs.add(m[1]);

// collect all source files
const all = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js|html)$/.test(e.name)) all.push(p); } })('src');

const counts = {};
const filesPerVar = {};
for (const f of all) {
  if (f.endsWith('main.css') || f.endsWith('variables.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const v of varDefs) {
    const escaped = v.replace(/[-]/g, '\\-');
    const re = new RegExp('var\\(' + escaped + '(?:[,\\)\\s])', 'g');
    const n = (t.match(re)||[]).length;
    if (n>0) { counts[v] = (counts[v]||0)+n; filesPerVar[v] = filesPerVar[v]||[]; filesPerVar[v].push(f); }
  }
}

console.log('=== variables.css 旧名：theme 文件是否已定义 / 全站消费数 ===');
for (const v of varDefs) {
  console.log((defs.has(v)?'DEFINED  ':'MISSING  ') + v + '  consumers=' + (counts[v]||0));
}
console.log('\n=== 消费方>0 且 MISSING（删文件会失样）===');
let m=0;
for (const v of varDefs) if(!defs.has(v) && counts[v]) { m++; console.log(v, counts[v], 'files:', filesPerVar[v].join(', ')); }
console.log('missing-with-consumers total:', m);
