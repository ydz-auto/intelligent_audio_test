/**
 * INT-1983 走查 W3：B3/B5 导入后音频行标签 + B7 列表刷新/标签筛选 + B8 空态与畸形 JSON
 */
import { connect, helpers, sleep } from './cdp.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const BASE = 'http://127.0.0.1:5650'
const OUT = './_walkthrough/int1983/shots'
mkdirSync(OUT, { recursive: true })

const { send, evaluate } = await connect()
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

const results = {}

// 搜索框定位
const searchInput = await evaluate(`(() => {
  const el = [...document.querySelectorAll('input[type="text"], input[type="search"]')].find(i => /搜索/.test(i.placeholder || ''))
  return el ? { placeholder: el.placeholder } : null
})()`)
log('[search]', JSON.stringify(searchInput))

const doSearch = async (kw) => {
  await evaluate(`(() => {
    const el = [...document.querySelectorAll('input[type="text"], input[type="search"]')].find(i => /搜索/.test(i.placeholder || ''))
    if (!el) return false
    el.value = ${JSON.stringify(kw)}
    el.dispatchEvent(new Event('input', { bubbles: true }))
    const btn = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === '搜索')
    if (btn) btn.click(); else el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    return true
  })()`)
  await sleep(3500)
}
const rowInfo = () => evaluate(`(() => {
  const rows = [...document.querySelectorAll('tbody tr')]
  return rows.slice(0, 3).map(r => r.innerText.replace(/\\s+/g, ' ').slice(0, 400))
})()`)

// ── B3：both 模式（接线测试_c1）行标签 ──
await doSearch('接线测试_c1')
results.B3_rows = await rowInfo()
log('[B3 rows]', JSON.stringify(results.B3_rows))
await screenshot(OUT, 'B3-list-row-tags.png')

// ── B5：json 模式（接线测试_c4）行标签（路径标签是否出现依赖后端 INT-1978） ──
await doSearch('接线测试_c4')
results.B5_rows = await rowInfo()
log('[B5 rows]', JSON.stringify(results.B5_rows))
await screenshot(OUT, 'B5-list-row-tags.png')

// ── B7：标签筛选下拉/标签云是否含新标签 ──
await doSearch('')
await sleep(2500)
results.B7_tagCloud = await evaluate(`(() => {
  const cloud = document.querySelector('.tag-cloud, [class*="tag-cloud"]')
  const text = cloud ? cloud.innerText : document.body.innerText.slice(0, 0)
  return {
    hasCloud: !!cloud,
    has手填A: /手填A/.test(text),
    hasJSON标签1: /JSON标签1/.test(text),
    hasJSON标签4: /JSON标签4/.test(text),
    excerpt: text.replace(/\\s+/g, ' ').slice(0, 400),
  }
})()`)
log('[B7]', JSON.stringify(results.B7_tagCloud))
await screenshot(OUT, 'B7-tag-cloud.png')

// ── B8-1：不选文件直接提交（开始上传应禁用） ──
await clickText('批量从文件夹导入')
await waitFor(`(${TOP})?.innerText.includes('批量从文件夹导入')`, 20000, 'folder modal')
await sleep(800)
results.B8_empty = await evaluate(`(() => {
  const top = ${TOP}
  const btn = [...top.querySelectorAll('button')].find(b => (b.textContent || '').includes('开始上传'))
  return { exists: !!btn, disabled: btn ? btn.disabled : null }
})()`)
log('[B8 empty]', JSON.stringify(results.B8_empty))
await screenshot(OUT, 'B8-empty-submit.png')

// ── B8-2：畸形 JSON 目录导入（应正常提示，无未捕获异常） ──
const doc = await send('DOM.getDocument', { depth: -1 })
const q = await send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: 'input[type="file"][webkitdirectory]' })
await send('DOM.setFileInputFiles', { nodeId: q.nodeId, files: [join(process.cwd(), '_walkthrough', 'int1983', 'data', '接线测试_畸形JSON')] })
await sleep(2000)
await clickText('开始上传')
await sleep(12000)
const exceptions = (await evaluate(`window.__probeExceptions || []`)) || []
results.B8_badJson = {
  pageHasImportDone: await evaluate(`document.body.innerText.includes('导入完成') || document.body.innerText.includes('完成并关闭')`),
  hasErrorBanner: await evaluate(`!!document.querySelector('[class*="error"]')`),
  exceptions,
}
log('[B8 bad json]', JSON.stringify(results.B8_badJson))
await screenshot(OUT, 'B8-bad-json-import.png')

writeFileSync('./_walkthrough/int1983/evidence-b7b8.json', JSON.stringify(results, null, 2))
console.log(JSON.stringify(results, null, 2))
process.exit(0)
