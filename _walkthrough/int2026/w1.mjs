/**
 * INT-2026 走查：用例编辑抽屉横向步骤导航编号是否连续
 * 连本 run dev server :5626（AUTH_MODE=dev → 常驻网关 :15000，真实库 intelligent_audio_test）
 * 覆盖：新增用例 API（四步）/ 端到端（五步）+ 编辑已有端到端用例（真实数据，五步），浅/深各一张
 */
import { connect, helpers, sleep } from '../int1983/cdp.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'

const BASE = 'http://127.0.0.1:5626'
const OUT = './_walkthrough/int2026/shots'
mkdirSync(OUT, { recursive: true })

const { send, evaluate, events } = await connect()
const { waitFor, screenshot, setDark } = helpers(send, evaluate)
await send('Runtime.enable')
await send('Page.enable')
await send('Network.enable')

const log = (...a) => console.error(...a)
const OVERLAY = `[...document.querySelectorAll('.modal-overlay')].slice(-1)[0]`

const toc = () => evaluate(`(() => {
  const root = ${OVERLAY} || document
  return [...root.querySelectorAll('.rce-step-toc .rce-toc-item')].map(i => ({
    num: (i.querySelector('.rce-toc-num')?.textContent || '').trim(),
    label: (i.querySelector('.rce-toc-label')?.textContent || '').trim(),
  }))
})()`)

const clickBtnText = (text) => evaluate(`(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim().includes(${JSON.stringify(text)}))
  if (!b) return false; b.click(); return true
})()`)

const pickTypeFilter = async (label) => {
  const ok = await evaluate(`(() => {
    const b = [...document.querySelectorAll('.badge-filter__badge')].find(x => (x.textContent || '').trim() === ${JSON.stringify(label)})
    if (!b) return false; b.click(); return true
  })()`)
  log('[filter]', label, ok)
  await sleep(2500)
  return ok
}

const closeTopModal = async () => {
  await evaluate(`(() => {
    const top = ${OVERLAY}
    const btn = top?.querySelector('.modal-close') || top?.querySelector('[class*="close"]')
    if (btn) { btn.click(); return true }
    return false
  })()`)
  await sleep(1200)
}

const openAdd = async () => {
  await clickBtnText('新增用例')
  await waitFor(`${OVERLAY} && ${OVERLAY}.querySelector('.rce-step-toc')`, 30000, 'add modal toc')
  await sleep(2000)
  await scrollToToc()
}

const scrollToToc = async () => {
  await evaluate(`(() => {
    const toc = (${OVERLAY} || document).querySelector('.rce-step-toc')
    if (!toc) return false
    toc.scrollIntoView({ block: 'start' })
    return true
  })()`)
  await sleep(900)
}

const openEditFirst = async () => {
  const editBtn = `[...document.querySelectorAll('button[title="编辑用例"]')]`
  await waitFor(`${editBtn}.length > 0`, 30000, 'case card edit action')
  const name = await evaluate(`(() => {
    const b = ${editBtn}[0]
    const card = b.closest('.test-case-card') || b.parentElement.parentElement
    return card ? (card.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean)[0] : ''
  })()`)
  await evaluate(`(() => { ${editBtn}[0].click(); return true })()`)
  await waitFor(`${OVERLAY} && ${OVERLAY}.querySelector('.rce-step-toc')`, 30000, 'edit modal toc')
  await sleep(2500)
  await scrollToToc()
  return name
}

// ── 登录（AUTH_MODE=dev，表单登录） ──
await send('Page.navigate', { url: 'about:blank' })
await sleep(600)
await send('Page.navigate', { url: `${BASE}/#/login` })
await sleep(3500)
if (await evaluate(`!!document.querySelector('input[type="password"]')`)) {
  await evaluate(`(() => {
    const u = document.querySelector('input[type="text"]')
    u.value = '接线测试_admin'; u.dispatchEvent(new Event('input', { bubbles: true }))
    const p = document.querySelector('input[type="password"]')
    p.value = 'JieXianTest@2026'; p.dispatchEvent(new Event('input', { bubbles: true }))
    document.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    return true
  })()`)
  await sleep(5000)
  await waitFor(`!location.hash.includes('/login')`, 25000, 'login redirect')
}
log('[login] hash =', await evaluate('location.hash'))

// ── 用例管理页（真实库数据） ──
await send('Page.navigate', { url: `${BASE}/#/testcases` })
await sleep(1200)
await send('Page.reload', {})
await sleep(3000)
await waitFor(`document.body.innerText.includes('测试用例列表')`, 60000, 'testcases page')
const listText = await evaluate(`document.body.innerText.slice(0, 500)`)
await setDark(false)
await screenshot(OUT, 'L1-testcases-list.png')

const result = {}

// ── A：新增用例 · API（四步） ──
await pickTypeFilter('API测试')
await openAdd()
result.A_add_api = await toc()
log('[A] 新增·API:', JSON.stringify(result.A_add_api))
await screenshot(OUT, 'A1-add-api-light.png')
await setDark(true)
await screenshot(OUT, 'A2-add-api-dark.png')
await setDark(false)
await closeTopModal()

// ── B：新增用例 · 端到端（五步） ──
await pickTypeFilter('端到端测试')
await openAdd()
result.B_add_e2e = await toc()
log('[B] 新增·端到端:', JSON.stringify(result.B_add_e2e))
await screenshot(OUT, 'B1-add-e2e-light.png')
await setDark(true)
await screenshot(OUT, 'B2-add-e2e-dark.png')
await setDark(false)
await closeTopModal()

// ── C：编辑已有端到端用例（真实数据，五步） ──
await pickTypeFilter('端到端测试')
result.C_case_name = await openEditFirst()
result.C_edit_e2e = await toc()
log('[C] 编辑·端到端:', result.C_case_name, JSON.stringify(result.C_edit_e2e))
await screenshot(OUT, 'C1-edit-e2e-light.png')
await setDark(true)
await screenshot(OUT, 'C2-edit-e2e-dark.png')
await setDark(false)

result.requests = events
  .filter((e) => e.method === 'Network.responseReceived')
  .map((e) => ({ status: e.params.response.status, url: e.params.response.url, type: e.params.type }))
  .filter((r) => r.url.includes('/api/'))
writeFileSync('./_walkthrough/int2026/result.json', JSON.stringify({ listText, result }, null, 2))
log('[done]', JSON.stringify({
  A: result.A_add_api.map((s) => s.num + ' ' + s.label),
  B: result.B_add_e2e.map((s) => s.num + ' ' + s.label),
  C: result.C_edit_e2e.map((s) => s.num + ' ' + s.label),
  caseName: result.C_case_name,
  apiRequests: result.requests.length,
}))
process.exit(0)
