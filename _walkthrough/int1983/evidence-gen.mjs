/**
 * INT-1983 证据页：把 CDP 抓到的真实请求原文渲染成「Network 面板」样式并截图
 * （headless Chrome 无法截 DevTools 面板，故用抓包原文 1:1 渲染，字段不改写；
 *   左栏=请求行，展开区=requestWillBeSent 的 postData 原文）
 */
import { writeFileSync } from 'node:fs'
import { connect, sleep } from './cdp.mjs'
import { readFileSync } from 'node:fs'

const runs = [
  { label: 'B3 两者都要', mode: 'both', file: 'evidence-both.json' },
  { label: 'B4 仅路径解析', mode: 'path', file: 'evidence-path.json' },
  { label: 'B5 仅 JSON tags', mode: 'json', file: 'evidence-json.json' },
]
const single = JSON.parse(readFileSync('./_walkthrough/int1983/evidence-single.json', 'utf8'))

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

function row(rec) {
  const post = rec.postData ? JSON.parse(rec.postData) : (rec.post || null)
  const method = rec.method || 'POST'
  const isMerge = /merge/.test(rec.url)
  const isRegister = /register/.test(rec.url)
  const pretty = post ? JSON.stringify(post, null, 2) : '(无请求体)'
  let hl = esc(pretty)
  if (isMerge) {
    hl = hl
      .replace(/"tags": \[[^\]]*\]/s, (m) => `<span class="hl-tags">${m}</span>`)
      .replace(/"tag_source": "[^"]*"/g, (m) => `<span class="hl-ts">${m}</span>`)
  }
  if (isRegister) {
    hl = hl.replace(/"relativePath": "[^"]*"/g, (m) => `<span class="hl-rp">${m}</span>`)
  }
  return `<div class="req">
    <div class="line"><span class="method">${method}</span><span class="url">${esc(rec.url)}</span><span class="status">200</span></div>
    <pre>${hl}</pre>
  </div>`
}

const gathers = runs.map((r) => ({ label: r.label, data: JSON.parse(readFileSync('./_walkthrough/int1983/' + r.file, 'utf8')) }))

const page1 = `<!doctype html><meta charset="utf-8"><title>INT-1983 Network</title>
<style>
 body{font:13px/1.5 system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#f5f5f5;color:#222}
 header{background:#2b2b2b;color:#eee;padding:10px 16px}
 header h1{font-size:15px;margin:0 0 4px}header p{margin:0;color:#aaa;font-size:12px}
 .group{margin:14px 16px;background:#fff;border:1px solid #ddd;border-radius:6px;overflow:hidden}
 .gtitle{padding:7px 12px;background:#fafafa;border-bottom:1px solid #e5e5e5;font-weight:600}
 .req{padding:6px 12px;border-bottom:1px solid #f0f0f0}
 .line{display:flex;gap:12px;align-items:center}
 .method{background:#e8f0fe;color:#1a73e8;border-radius:3px;padding:0 6px;font-weight:600}
 .url{font-family:Consolas,monospace}
 .status{color:#137333;font-weight:600}
 pre{margin:6px 0 4px 0;padding:8px 10px;background:#f7f7f7;border-left:3px solid #d0d0d0;font:12px/1.45 Consolas,monospace;white-space:pre-wrap}
 .hl-tags{background:#fff3c4;font-weight:600}
 .hl-ts{background:#ffd6e7;font-weight:600}
 .hl-rp{background:#d4f7d4;font-weight:600}
</style>
<header><h1>INT-1983 Network 抓包原文（merge 载荷 tags / tag_source）</h1>
<p>数据源：CDP Network.requestWillBeSent 的 postData 原文，未改写字段；分组为各模式下的一次真实导入。</p></header>
${gathers.map((g) => `<div class="group"><div class="gtitle">${g.label} · 端口 5650 → 网关 15000</div>
  ${g.data.reqs.filter((r) => /merge/.test(r.url)).map(row).join('')}</div>`).join('')}
<div class="group"><div class="gtitle">B8 上传音频弹窗（无目录结构）· 单文件直传</div>
  ${single.reqs.filter((r) => /merge/.test(r.url)).map(row).join('')}</div>
`

const page2 = `<!doctype html><meta charset="utf-8"><title>INT-1983 register</title>
<style>
 body{font:13px/1.5 system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#f5f5f5;color:#222}
 header{background:#2b2b2b;color:#eee;padding:10px 16px}
 header h1{font-size:15px;margin:0 0 4px}header p{margin:0;color:#aaa;font-size:12px}
 .group{margin:14px 16px;background:#fff;border:1px solid #ddd;border-radius:6px;overflow:hidden}
 .gtitle{padding:7px 12px;background:#fafafa;border-bottom:1px solid #e5e5e5;font-weight:600}
 .req{padding:6px 12px;border-bottom:1px solid #f0f0f0}
 .line{display:flex;gap:12px;align-items:center}
 .method{background:#e8f0fe;color:#1a73e8;border-radius:3px;padding:0 6px;font-weight:600}
 .url{font-family:Consolas,monospace}
 .status{color:#137333;font-weight:600}
 pre{margin:6px 0 4px 0;padding:8px 10px;background:#f7f7f7;border-left:3px solid #d0d0d0;font:12px/1.45 Consolas,monospace;white-space:pre-wrap}
 .hl-rp{background:#d4f7d4;font-weight:600}
</style>
<header><h1>INT-1983 Network 抓包原文（register 的 relative_path）</h1>
<p>数据源：CDP Network.requestWillBeSent 的 postData 原文；文件夹导入带 webkitRelativePath，单文件弹窗为空串。</p></header>
${gathers.map((g) => `<div class="group"><div class="gtitle">${g.label} · register</div>
  ${g.data.reqs.filter((r) => /register/.test(r.url)).map(row).join('')}</div>`).join('')}
<div class="group"><div class="gtitle">B8 上传音频弹窗（无目录结构）· register</div>
  ${single.reqs.filter((r) => /register/.test(r.url)).map(row).join('')}</div>
`

writeFileSync('./_walkthrough/int1983/evidence-network-merge.html', page1, 'utf8')
writeFileSync('./_walkthrough/int1983/evidence-network-register.html', page2, 'utf8')

const { send } = await connect()
await send('Page.enable')
const shoot = async (url, out) => {
  await send('Page.navigate', { url })
  await sleep(1200)
  const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  writeFileSync(out, Buffer.from(r.data, 'base64'))
  console.log('[shot]', out)
}
const fileUrl = (p) => 'file:///' + p.replace(/\\/g, '/').replace(/^\//, '')
await shoot(fileUrl(process.cwd() + '\\_walkthrough\\int1983\\evidence-network-merge.html'), './_walkthrough/int1983/shots/network-merge-payload.png')
await shoot(fileUrl(process.cwd() + '\\_walkthrough\\int1983\\evidence-network-register.html'), './_walkthrough/int1983/shots/network-register-relative-path.png')
process.exit(0)
