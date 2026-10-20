import fs from 'node:fs';
import path from 'node:path';

// 检查 theme.css/theme-presets.css 是否被误改（它们不应含旧名 var() 引用）
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css','src/assets/styles/variables.css']) {
  const t = fs.readFileSync(f,'utf8');
  const olds = ['--primary-color','--text-secondary','--border-color','--text-primary','--border-radius-md','--background-primary','--danger-color','--primary-light','--secondary-color','--background-secondary'];
  let n = 0;
  for (const v of olds) {
    const re = new RegExp('var\\(\\s*'+v.replace(/[-]/g,'\\-')+'(?:[,)])','g');
    n += (t.match(re)||[]).length;
  }
  console.log(f, 'old-var refs:', n);
}

// 剩余所有 variables.css 中定义、但消费方仍使用旧名的引用
const varsCss = fs.readFileSync('src/assets/styles/variables.css','utf8');
const rootMatch = varsCss.match(/:root\s*\{([\s\S]*?)\}/);
const body = rootMatch ? rootMatch[1] : varsCss;
const defs = {};
for (const m of body.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) defs[m[1].trim()] = m[2].trim();

// theme 文件定义（正源）
const themeDefs = new Set();
for (const f of ['src/assets/styles/theme.css','src/assets/styles/theme-presets.css','src/assets/styles/base/base.css','src/assets/styles/base/utilities.css']) {
  const t = fs.readFileSync(f,'utf8');
  for (const m of t.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) themeDefs.add(m[1]);
}

// 全库消费统计（排除 variables.css 自身）
const allFiles = [];
(function walk(d){ for (const e of fs.readdirSync(d,{withFileTypes:true})) { const p = path.join(d,e.name); if (e.isDirectory()) walk(p); else if (/\.(css|vue|ts|js)$/.test(e.name)) allFiles.push(p); } })('src');

const remaining = {};
for (const f of allFiles) {
  if (f.endsWith('variables.css') || f.endsWith('main.css')) continue;
  const t = fs.readFileSync(f,'utf8');
  for (const v of Object.keys(defs)) {
    const re = new RegExp('var\\(\\s*'+v.replace(/[-]/g,'\\-')+'(?:[,)])','g');
    const n = (t.match(re)||[]).length;
    if (n>0) remaining[v] = (remaining[v]||0)+n;
  }
}
console.log('\n=== 删除 variables.css 后仍会「用了没定义」的引用 ===');
let total=0;
for (const [v,n] of Object.entries(remaining).sort((a,b)=>b[1]-a[1])) {
  console.log(`${v}: ${n}  (theme defined: ${themeDefs.has(v)})`);
  total+=n;
}
console.log('total remaining:', total);
