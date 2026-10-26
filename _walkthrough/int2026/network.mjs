/**
 * INT-2026 Network 证据：抓用例管理页打开抽屉期间的真实 /api 请求（方法/URL/状态），
 * headless 无法截 DevTools 面板，故按抓包原文渲染成 Network 面板样式再截图。
 */
import { connect, helpers, sleep } from '../int1983/cdp.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'

const BASE = 'http://127.0.0.1:5626'
const OUT = './_walkthrough/int2026/shots'
mkdirSync(OUT, { recursive: true })

const { send, evaluate, events } = await connect()
const { waitFor, screenshot } = helpers(send, evaluate)
await send('Runtime.enable')
await send('Page.enable')
await send('Network.enable')
const OVERLAY = `[...document.querySelectorAll('.modal-overlay')].slice(-1)[0]`
const log = (...a) => console.error(...a)

await send('Page.navigate', { url: `${BASE}/#/testcases` })
await sleep(1200)
await send('Page.reload', {})
await sleep(3000)
await waitFor(`document.body.innerText.includes('测试用例列表')`, 60000, 'testcases page')

// 打开端到端新增抽屉，触发详情/维度接口
await evaluate(`(() => {
  const b = [...document.querySelectorAll('.badge-filter__badge')].find(x => (x.textContent || '').trim() === '端到端测试')
  if (b) b.click(); return true
})()`)
await sleep(2500)
await evaluate(`(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim().includes('新增用例'))
  if (b) b.click(); return true
})()`)
await waitFor(`${OVERLAY} && ${OVERLAY}.querySelector('.rce-step-toc')`, 30000, 'add modal toc')
await sleep(3000)

const reqs = []
for (const ev of events) {
  if (ev.method !== 'Network.requestWillBeSent') continue
  const r = ev.params.request
  if (!r.url.includes('/api/v1/')) continue
  reqs.push({ id: ev.params.requestId, method: r.method, url: r.url, status: null })
}
const byId = new Map(reqs.map((r) => [r.id, r]))
const scanStatus = () => {
  for (const ev of events) {
    if (ev.method !== 'Network.responseReceived') continue
    const hit = byId.get(ev.params.requestId)
    if (hit) hit.status = ev.params.response.status
  }
}
scanStatus()
if (reqs.some((r) => r.status === null)) {
  log('[net] 有请求未收尾，等 4s 再扫')
  await sleep(4000)
  scanStatus()
}
// 去重：同 URL 同方法只留一条（取最后一次状态）

const uniq = [...new Map(reqs.map((r) => [r.method + ' ' + r.url, r])).values()]
log('[net]', uniq.length, 'unique requests')
const rows = uniq.map((r) => {
  const u = new URL(r.url)
  const ok = r.status && r.status < 400
  return `<tr><td class="${ok ? 'ok' : 'bad'}">${r.status ?? 0}</td><td>${r.method}</td><td>${u.pathname}${u.search}</td></tr>`
}).join('\n')

const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Network · INT-2026</title>
<style>
  body { margin:0; background:#202124; color:#e8eaed; font:13px/1.6 "Segoe UI",system-ui,sans-serif; }
  header { padding:14px 20px; border-bottom:1px solid #3c4043; background:#292a2d; }
  h1 { margin:0 0 4px; font-size:16px; font-weight:600; }
  .sub { color:#9aa0a6; font-size:12px; }
  table { width:100%; border-collapse:collapse; }
  th, td { text-align:left; padding:7px 14px; border-bottom:1px solid #2f3033; }
  th { position:sticky; top:0; background:#2b2c2f; color:#9aa0a6; font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  td { font-family:Consolas,"Courier New",monospace; font-size:12.5px; }
  .ok { color:#81c995; font-weight:600; } .bad { color:#f28b82; font-weight:600; }
  tr:hover td { background:#2a2b2e; }
</style></head><body>
<header>
  <h1>Network — INT-2026 用例编辑抽屉（http://127.0.0.1:5626，真实网关 :15000 / 库 intelligent_audio_test）</h1>
  <div class="sub">操作：打开 /#/testcases → 类型筛选「端到端测试」→ 点「新增用例」→ 抽屉渲染步骤导航。以下为该过程真实请求（与方法/URL 去重，共 ${uniq.length} 条）。</div>
</header>
<table><thead><tr><th style="width:80px">Status</th><th style="width:80px">Method</th><th>Request URL</th></tr></thead><tbody>
${rows}
</tbody></table></body></html>`

writeFileSync('./_walkthrough/int2026/network.html', html)
await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1100, deviceScaleFactor: 1, mobile: false })
await send('Page.navigate', { url: 'file:///D:/00_user_data/multica_workspaces_desktop-api.multica.ai/intelligent-95ba6a12369f/int-2026-13a823f69aaf/worktree/_walkthrough/int2026/network.html' })
await sleep(1500)
await screenshot(OUT, 'N1-network.png')
const bad = uniq.filter((r) => !r.status || r.status >= 400)
log('[net] non-2xx:', JSON.stringify(bad))
writeFileSync('./_walkthrough/int2026/network.json', JSON.stringify(uniq, null, 2))
process.exit(0)
