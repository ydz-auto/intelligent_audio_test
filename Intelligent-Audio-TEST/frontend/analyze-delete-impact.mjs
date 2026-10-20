import fs from 'node:fs';
import path from 'node:path';

// 1) Gather all var(--x) references across src (exclude main.css & variables.css)
// 2) Gather all definitions from: theme.css, theme-presets.css, base/*, plus any :root/{data-} blocks inside component css/vue?
//    -> For correctness: collect ALL custom property definitions anywhere (varDefs per file), then compute which are "defined globally".

const SRC = 'src';
const all = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js|html)$/.test(e.name)) all.push(p); } })(SRC);

// Global definitions: only theme files + base are guaranteed loaded via index.css chain.
const globalFiles = [
  'src/assets/styles/theme.css',
  'src/assets/styles/theme-presets.css',
  'src/assets/styles/base/index.css',
  'src/assets/styles/base/reset.css',
  'src/assets/styles/base/base.css',
  'src/assets/styles/base/utilities.css',
];
const globalDefs = new Set();
for (const f of globalFiles) {
  if (!fs.existsSync(f)) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) globalDefs.add(m[1]);
}

// Also variables.css currently provides aliases; simulate AFTER deletion by excluding it.
// References (excluding main.css & variables.css themselves)
const refs = {}; // var -> { total, noFallback, files: {file:count} }
for (const f of all) {
  if (f.includes('assets/styles/main.css') || f.includes('assets/styles/variables.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)([^)]*)\)/g)) {
    const v = m[1];
    const hasFallback = m[2].trim().startsWith(',');
    if (!refs[v]) refs[v] = { total:0, noFallback:0, files:{} };
    refs[v].total++;
    if (!hasFallback) refs[v].noFallback++;
    refs[v].files[f] = (refs[v].files[f]||0)+1;
  }
}

// Report vars referenced but NOT globally defined (post-variables.css-deletion)
const missing = Object.entries(refs)
  .filter(([v]) => !globalDefs.has(v))
  .sort((a,b) => b[1].total - a[1].total);

console.log('=== 删除 variables.css 后「用了没定义」的变量（全库）===');
console.log('globalDefs count (theme/base):', globalDefs.size);
console.log('referenced vars total:', Object.keys(refs).length, '| missing:', missing.length);
let noFbTotal = 0, totalRefs = 0;
for (const [v,s] of missing) { noFbTotal += s.noFallback; totalRefs += s.total; }
console.log(`missing refs: total=${totalRefs} noFallback=${noFbTotal}`);
console.log('\nTop 40 missing by total:');
for (const [v,s] of missing.slice(0,40)) {
  console.log(`${v}: total=${s.total} noFb=${s.noFallback} files=${Object.keys(s.files).length}`);
}

// Files distribution of no-fallback missing refs
const fileNoFb = {};
for (const [v,s] of missing) {
  for (const [f,n] of Object.entries(s.files)) {
    // recompute noFallback count per file per var
    const t = fs.readFileSync(f,'utf8');
    let nf = 0;
    for (const m of t.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)([^)]*)\)/g)) {
      if (m[1]===v && !m[2].trim().startsWith(',')) nf++;
    }
    if (nf>0) fileNoFb[f] = (fileNoFb[f]||0) + nf;
  }
}
console.log('\n=== 无 fallback 引用按文件（删除后必失样）===');
for (const [f,n] of Object.entries(fileNoFb).sort((a,b)=>b[1]-a[1])) {
  console.log(`${String(n).padStart(4)}  ${f}`);
}
console.log('\nfiles with noFallback refs:', Object.keys(fileNoFb).length);
