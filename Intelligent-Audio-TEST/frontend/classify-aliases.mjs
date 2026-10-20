import fs from 'node:fs';
import path from 'node:path';

// Parse variables.css definitions: for each alias var -> its definition source
const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const defs = {}; // alias -> definition string
// Only parse :root { ... } block
const rootMatch = varsCss.match(/:root\s*\{([\s\S]*?)\}/);
const body = rootMatch ? rootMatch[1] : varsCss;
for (const m of body.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) {
  defs[m[1].trim()] = m[2].trim();
}

// Classify: direct alias (definition is var(--new) or var(--new, fb)) vs composite
const direct = {}; const composite = [];
for (const [alias, def] of Object.entries(defs)) {
  const m = def.match(/^var\(\s*(--[a-zA-Z0-9-]+)([^)]*)\)$/);
  if (m && !m[1].startsWith('--color-')) {
    direct[alias] = m[1]; // alias -> target new var
  } else {
    composite.push({alias, def});
  }
}

console.log('=== 直接别名（可全局替换 var(alias) → var(target)）===');
for (const [a,t] of Object.entries(direct)) console.log(`  ${a} -> ${t}`);
console.log('direct count:', Object.keys(direct).length);

console.log('\n=== 复合值（需提级保留或展开）===');
for (const c of composite) console.log(`  ${c.alias}: ${c.def}`);
console.log('composite count:', composite.length);

// Verify: are direct targets defined in theme files?
const globalDefs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css']) {
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) globalDefs.add(m[1]);
}
console.log('\n=== 直接别名 target 是否在 theme 定义 ===');
for (const [a,t] of Object.entries(direct)) {
  if (!globalDefs.has(t)) console.log(`  WARN: ${a} -> ${t} NOT in theme files`);
}
