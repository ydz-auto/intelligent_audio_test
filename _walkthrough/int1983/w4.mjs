/**
 * INT-1983 走查 W4：上传音频弹窗（无目录结构）单文件导入 —— 载荷核对 + B8 无目录结构提示
 */
import { connect, helpers, sleep } from './cdp.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const BASE = 'http://127.0.0.1:5650'
const OUT = './_walkthrough/int1983/shots'
mkdirSync(OUT, { recursive: true })

const { send, evaluate, events } = await connect()
const { waitFor, screenshot } = helpers(send, evaluate)
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

await clickText('上传音频')
await waitFor(`(${TOP})?.innerText.includes('上传音频')`, 20000, 'upload modal')
await sleep(800)

const doc = await send('DOM.getDocument', { depth: -1 })
const q = await send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: 'input[type="file"]:not([webkitdirectory])' })
await send('DOM.setFileInputFiles', {
  nodeId: q.nodeId,
  files: [join(process.cwd(), '_walkthrough', 'int1983', 'data', '接线测试_单文件', process.argv[2] || '接线测试_s2.wav')],
})
await sleep(2000)

// 手填标签
await evaluate(`(() => {
  const items = [...(${TOP})?.querySelectorAll('.option-item') || []]
  const item = items.find(x => (x.querySelector('label')?.innerText || '').trim() === '标签')
  const input = item?.querySelector('input[type="text"]')
  if (!input) return false
  input.value = '手填A'; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }))
  return true
})()`)
await sleep(300)
const picked = await evaluate(`(${TOP})?.querySelector('[data-field="tagSource"] input:checked')?.value`)
await screenshot(OUT, 'B8-单文件-上传弹窗.png')

await clickText('开始上传')
// 等 merge
const start = Date.now()
let got = false
while (Date.now() - start < 90000) {
  if (events.some(e => e.method === 'Network.responseReceived' && /\/audios\/upload\/merge/.test(e.params.response.url || ''))) { got = true; break }
  await sleep(500)
}
await sleep(4000)
const reqs = []
for (const e of events) {
  if (e.method !== 'Network.requestWillBeSent') continue
  const url = e.params.request.url || ''
  if (!/\/api\/v1\/audios\/(upload\/)?(register|merge)/.test(url)) continue
  reqs.push({ url: url.replace(BASE, ''), post: e.params.request.postData ? JSON.parse(e.params.request.postData) : null })
}
const resps = []
for (const e of events) {
  if (e.method !== 'Network.responseReceived') continue
  const url = e.params.response.url || ''
  if (!/\/api\/v1\/audios\/(upload\/)?(register|merge)/.test(url)) continue
  let body = ''
  try { body = (await send('Network.getResponseBody', { requestId: e.params.requestId })).body.slice(0, 300) } catch {}
  resps.push({ url: url.replace(BASE, ''), status: e.params.response.status, body })
}
writeFileSync('./_walkthrough/int1983/evidence-single.json', JSON.stringify({ picked, reqs, resps }, null, 2))
log('[net]', JSON.stringify(reqs, null, 2))
log('[resps]', JSON.stringify(resps, null, 2))
await screenshot(OUT, 'B8-单文件-完成后.png')
await sleep(3000)
const pageText = await evaluate(`document.body.innerText.slice(0, 400)`)
console.log(JSON.stringify({ picked, gotMerge: got, reqs, resps, pageHead: pageText }, null, 2))
process.exit(0)
