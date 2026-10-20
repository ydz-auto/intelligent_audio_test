import fs from 'node:fs';
import path from 'node:path';

const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const varDefs = [];
for (const m of varsCss.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) varDefs.push(m[1]);

const defs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css','src/assets/styles/base/base.css','src/assets/styles/base/utilities.css']) {
  try { const t = fs.readFileSync(f,'utf8'); for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) defs.add(m[1]); } catch(e){}
}

const all = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js|html)$/.test(e.name)) all.push(p); } })('src');

// For each MISSING var, count total refs, refs WITHOUT fallback, refs WITH fallback
const stats = {};
for (const f of all) {
  if (f.endsWith('main.css') || f.endsWith('variables.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const v of varDefs) {
    if (defs.has(v)) continue;
    const escaped = v.replace(/[-]/g, '\\-');
    // match var(--x) or var(--x, ...)
    const re = new RegExp('var\\(\\s*' + escaped + '(\\s*[,)])', 'g');
    let m;
    while ((m = re.exec(t)) !== null) {
      const hasFallback = m[1].includes(',');
      if (!stats[v]) stats[v] = { total:0, noFallback:0, withFallback:0, files:{} };
      stats[v].total++;
      if (hasFallback) stats[v].withFallback++; else stats[v].noFallback++;
      stats[v].files[f] = (stats[v].files[f]||0)+1;
    }
  }
}

console.log('=== theme 未定义旧名：引用总数 / 无 fallback / 有 fallback ===');
const entries = Object.entries(stats).filter(([v,s])=>s.noFallback>0).sort((a,b)=>b[1].noFallback-a[1].noFallback);
for (const [v,s] of entries) {
  console.log(`${v}: total=${s.total} noFallback=${s.noFallback} withFallback=${s.withFallback}`);
}
console.log('\n=== 无 fallback 引用按文件分布（需要改名的）===');
const fileNoFb = {};
for (const [v,s] of Object.entries(stats)) {
  for (const [f,n] of Object.entries(s.files)) {
    // need per-file noFallback count
    const t = fs.readFileSync(f,'utf8');
    const escaped = v.replace(/[-]/g, '\\-');
    const re = new RegExp('var\\(\\s*' + escaped + '(\\s*[,)])', 'g');
    let m, nf=0;
    while ((m = re.exec(t)) !== null) if (!m[1].includes(',')) nf++;
    if (nf>0) fileNoFb[f] = (fileNoFb[f]||0) + nf;
  }
}
for (const [f,n] of Object.entries(fileNoFb).sort((a,b)=>b[1]-a[1])) console.log(`${String(n).padStart(4)}  ${f}`);
console.log('\ntotal no-fallback refs:', Object.values(stats).reduce((a,s)=>a+s.noFallback,0));
