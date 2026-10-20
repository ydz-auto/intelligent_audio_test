import fs from 'node:fs';

// Build exact replacement map: old alias -> target expression used in var()
const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const rootMatch = varsCss.match(/:root\s*\{([\s\S]*?)\}/);
const body = rootMatch ? rootMatch[1] : varsCss;
const defs = {};
for (const m of body.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) {
  defs[m[1].trim()] = m[2].trim();
}

// Determine: direct alias (var(--x) where x defined in theme) -> replace consumption var(--old) with var(--new)
// Composite/standalone values -> these must be "promoted" to theme-presets.css (kept as definition)
const themeDefs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css']) {
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) themeDefs.add(m[1]);
}

const direct = {}; // old -> new target
const composite = []; // {alias, def}
for (const [alias, def] of Object.entries(defs)) {
  const m = def.match(/^var\(\s*(--[a-zA-Z0-9-]+)([^)]*)\)$/);
  if (m) {
    direct[alias] = m[1];
  } else {
    composite.push({alias, def});
  }
}

console.log('=== 直接别名（消费 var(--old) → var(--new)）===');
for (const [a,t] of Object.entries(direct)) console.log(`  ${a} -> ${t}`);
console.log('count:', Object.keys(direct).length);

console.log('\n=== 复合/独立值（需提级保留进 theme-presets.css）===');
for (const c of composite) console.log(`  ${c.alias}: ${c.def}`);
console.log('count:', composite.length);

// Count consumption per direct alias (no-fallback) across src
const allFiles = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = d+'/'+e.name; if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js)$/.test(e.name)) allFiles.push(p); } })('src');

const cons = {};
for (const f of allFiles) {
  if (f.endsWith('/variables.css') || f.endsWith('/main.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const [a,newT] of Object.entries(direct)) {
    const re = new RegExp('var\\(\\s*'+a.replace(/[-]/g,'\\-')+'(\\s*[,)])','g');
    const n = (t.match(re)||[]).length;
    if (n>0) cons[a] = (cons[a]||0)+n;
  }
}
console.log('\n=== 直接别名消费总量 ===');
let total = 0;
for (const [a,n] of Object.entries(cons).sort((x,y)=>y[1]-x[1])) { console.log(`  ${a} -> ${direct[a]}: ${n}`); total+=n; }
console.log('direct total:', total);
