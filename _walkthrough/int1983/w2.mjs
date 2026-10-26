/**
 * INT-1983 走查 W2：B3 / B4 / B5 —— 文件夹导入三种「标签来源」，抓 register / merge 真实载荷
 * 用法：node w2.mjs <both|path|json> <data 目录名>
 */
import { connect, helpers, sleep } from './cdp.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const BASE = 'http://127.0.0.1:5650'
const OUT = './_walkthrough/int1983/shots'
mkdirSync(OUT, { recursive: true })

const mode = process.argv[2] || 'both'
const dirName = process.argv[3] || '接线测试_组1'
const dataDir = join(process.cwd(), '_walkthrough', 'int1983', 'data', dirName)

const { send, evaluate, events } = await connect()
const { waitFor, screenshot, setDark } = helpers(send, evaluate)
await send('Runtime.enable')
await send('Page.enable')
await send('Network.enable')
await send('DOM.enable')

const log = (...a) => console.error(...a)
const TOP = `[...document.querySelectorAll('.modal-overlay')].slice(-1)[0]`
const clickText = (text) => evaluate(`(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim().includes(${JSON.stringify(text)}))
  if (!b) return false; b.click(); return true
})()`)

// ── 准备页面 ──
await send('Page.navigate', { url: 'about:blank' })
await sleep(700)
await send('Page.navigate', { url: `${BASE}/#/audio-import` })
await sleep(3500)
if (await evaluate(`!!document.querySelector('input[type="password"]')`)) {
  await evaluate(`(() => {
    const u=document.querySelector('input[type="text"]');u.value='admin';u.dispatchEvent(new Event('input',{bubbles:true}))
    const p=document.querySelector('input[type="password"]');p.value='admin123';p.dispatchEvent(new Event('input',{bubbles:true}))
    document.querySelector('form')?.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));return true})()`)
  await sleep(4000)
  await send('Page.navigate', { url: `${BASE}/#/audio-import` })
  await sleep(3000)
}
await waitFor(`document.body.innerText.includes('音频管理')`, 30000, 'audio page')

// 打开文件夹导入弹窗并选中真实目录
await clickText('批量从文件夹导入')
await waitFor(`(${TOP})?.innerText.includes('批量从文件夹导入')`, 20000, 'folder modal')
await sleep(800)
const doc = await send('DOM.getDocument', { depth: -1 })
const q = await send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: '.modal-overlay:last-of-type input[type="file"][webkitdirectory]' })
const nodeId = q.nodeId || (await send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: 'input[type="file"][webkitdirectory]' })).nodeId
await send('DOM.setFileInputFiles', { nodeId, files: [dataDir] })
await sleep(2000)
log('[files] stats:', (await evaluate(`(${TOP})?.querySelector('.file-stats')?.innerText?.replace(/\\n/g,' | ')`)) || '')

// 手填标签 + 标签来源
await evaluate(`(() => {
  const items = [...(${TOP})?.querySelectorAll('.option-item') || []]
  const item = items.find(x => (x.querySelector('label')?.innerText || '').trim() === '标签')
  const input = item?.querySelector('input[type="text"]')
  if (!input) return false
  input.value = '手填A'; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }))
  return true
})()`)
await sleep(300)
await evaluate(`(() => {
  const r = (${TOP})?.querySelector('[data-field="tagSource"] input[value="${mode}"]')
  if (!r) return false; r.click(); return r.checked
})()`)
await sleep(400)
const picked = await evaluate(`(${TOP})?.querySelector('[data-field="tagSource"] input:checked')?.value`)
log('[ui] picked tagSource =', picked)
await screenshot(OUT, `B3B4B5-${mode}-before-upload.png`)

// 开始上传
const t0 = Date.now()
await clickText('开始上传')
// 等 merge 请求出现
const waitMerge = async (timeoutMs = 120000) => {
  const start = Date.now()
  for (;;) {
    const hit = events.some(e => e.method === 'Network.responseReceived' && /\/audios\/upload\/merge/.test(e.params.response.url || ''))
    if (hit) return true
    if (Date.now() - start > timeoutMs) return false
    await sleep(500)
  }
}
const gotMerge = await waitMerge()
log('[net] merge seen:', gotMerge, 'elapsed(ms):', Date.now() - t0)
await sleep(4000)

// 汇总请求
const reqs = []
for (const e of events) {
  if (e.method !== 'Network.requestWillBeSent') continue
  const url = e.params.request.url || ''
  if (!/\/api\/v1\/audios\/(upload\/)?(register|merge|init)/.test(url)) continue
  reqs.push({ url: url.replace(BASE, ''), method: e.params.request.method, postData: e.params.request.postData || null, requestId: e.params.requestId })
}
const resps = []
for (const e of events) {
  if (e.method !== 'Network.responseReceived') continue
  const url = e.params.response.url || ''
  if (!/\/api\/v1\/audios\/(upload\/)?(register|merge|init)/.test(url)) continue
  let body = ''
  try { body = (await send('Network.getResponseBody', { requestId: e.params.requestId })).body.slice(0, 600) } catch {}
  resps.push({ url: url.replace(BASE, ''), status: e.params.response.status, body })
}
const summary = { mode, dirName, picked, reqs, resps }
writeFileSync(`./_walkthrough/int1983/evidence-${mode}.json`, JSON.stringify(summary, null, 2))
log('[net]', JSON.stringify(reqs.map(r => ({ url: r.url, post: r.postData ? JSON.parse(r.postData) : null })).slice(0, 6), null, 2))

// 等列表刷新
await sleep(6000)
const pageText = await evaluate(`document.body.innerText.slice(0, 1500)`)
await screenshot(OUT, `B${mode === 'both' ? 3 : mode === 'path' ? 4 : 5}-${mode}-after-upload.png`)

console.log(JSON.stringify({ mode, picked, gotMerge, reqCount: reqs.length, reqs: reqs.map(r => ({ url: r.url, post: r.postData ? JSON.parse(r.postData) : null })), resps, pageHead: pageText.slice(0, 600) }, null, 2))
process.exit(0)
