import fs from 'node:fs';
import path from 'node:path';

// theme file definitions (source of truth for targets)
const themeDefs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css']) {
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) themeDefs.add(m[1]);
}

// variables.css aliases
const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const rootMatch = varsCss.match(/:root\s*\{([\s\S]*?)\}/);
const body = rootMatch ? rootMatch[1] : varsCss;
const defs = {};
for (const m of body.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) defs[m[1].trim()] = m[2].trim();

// All referenced vars (consumers) across src
const allFiles = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js)$/.test(e.name)) allFiles.push(p); } })('src');

const consumers = {}; // var -> count
for (const f of allFiles) {
  if (f.endsWith('variables.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)) {
    const v = m[1];
    if (!(v in defs)) continue; // only vars defined in variables.css
    consumers[v] = (consumers[v]||0)+1;
  }
}

console.log('=== 变量分类：删除 variables.css 后是否仍可解析 ===');
const categories = { directOk: [], directMissing: [], composite: [] };
for (const [alias, def] of Object.entries(defs)) {
  const m = def.match(/^var\(\s*(--[a-zA-Z0-9-]+)([^)]*)\)$/);
  const used = consumers[alias] || 0;
  if (m) {
    if (themeDefs.has(m[1])) categories.directOk.push({alias, target: m[1], used});
    else categories.directMissing.push({alias, target: m[1], used, def});
  } else {
    categories.composite.push({alias, def, used});
  }
}

console.log('\n-- A. 直接别名 & target 已在 theme 定义（消费方直接替换）--');
for (const c of categories.directOk) console.log(`  ${c.alias} -> ${c.target}  (used=${c.used})`);

console.log('\n-- B. 直接别名但 target 不在 theme（需先提级 target 或改映射）--');
for (const c of categories.directMissing) console.log(`  ${c.alias} -> ${c.target}  (used=${c.used}) def="${c.def}"`);

console.log('\n-- C. 复合值（消费方不能简单替换，需提级定义）--');
for (const c of categories.composite) console.log(`  ${c.alias}: ${c.def}  (used=${c.used})`);

// vars defined in variables.css but never consumed
const allDefined = Object.keys(defs);
const usedSet = new Set(Object.keys(consumers));
console.log('\n-- 定义但无消费（可随文件删除）--');
for (const v of allDefined) if (!usedSet.has(v)) console.log(`  ${v}`);
