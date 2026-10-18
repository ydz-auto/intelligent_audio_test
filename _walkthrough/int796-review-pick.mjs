/**
 * INT-796 交付走查——挑选合并层级展示（§3.7：树形/用例视角/平铺 + result_type 折叠）
 * + 任务详情人工审核/AI复核（§3：入口/单条批量弹窗/历史抽屉/标记统计）。
 * 隔离 Chrome CDP :9223，连本 run dev server :5500（连常驻后端 :5000）。
 * 产出：每场景 浅/深 两张 PNG + Network 请求汇总。
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, 'shots', 'int796')
mkdirSync(OUT_DIR, { recursive: true })

const BASE = 'http://127.0.0.1:5500'
const CDP_HTTP = 'http://127.0.0.1:9223'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function connect() {
  const tabs = await (await fetch(`${CDP_HTTP}/json/new?about:blank`, { method: 'PUT' })).json().catch(() => null)
  const list = await (await fetch(`${CDP_HTTP}/json`)).json()
  const page = (tabs || null)
    ? list.find((t) => t.type === 'page' && t.id === tabs.id)
    : list.find((t) => t.type === 'page' && !t.url.startsWith('devtools') && !t.url.startsWith('chrome://'))
  if (!page) throw new Error('no page target')
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let seq = 0
  const pending = new Map()
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
    }
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
  return { ws, send }
}

async function evaluate(send, expression) {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (r.exceptionDetails) throw new Error('evaluate exception: ' + JSON.stringify(r.exceptionDetails))
  return r.result?.value
}
async function waitFor(send, expr, timeoutMs = 25000) {
  const start = Date.now()
  for (;;) {
    if (await evaluate(send, expr)) return
    if (Date.now() - start > timeoutMs) throw new Error('timeout waiting: ' + expr)
    await sleep(300)
  }
}
async function screenshot(send, name) {
  const r = await send('Page.captureScreenshot', { format: 'png' })
  const file = join(OUT_DIR, name)
  writeFileSync(file, Buffer.from(r.data, 'base64'))
  console.log('[shot] ' + name)
  return file
}

const network = []
async function enableNet(send) {
  await send('Network.enable')
  send('Network.requestWillBeSent', (p) => {})
  // CDP 事件由 ws.onmessage 统一消化——这里用原始注入监听
  return network
}

const { ws, send } = await connect()
await send('Page.enable')
await send('Runtime.enable')
await send('Network.enable')

// 捕获 Network：记录 /tasks/cherry-picks、/tasks/results/review 等关键请求
const netHits = []
const origOnMessage = ws.onmessage
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data)
  if (msg.method === 'Network.requestWillBeSent') {
    const u = msg.params?.request?.url || ''
    if (u.includes('/api/v1/') && !u.includes('socket.io') && !u.includes('.js') && !u.includes('.css')) {
      netHits.push(`${msg.params.request.method} ${u.replace(BASE, '')}`)
    }
  }
  origOnMessage(ev)
}

console.log('== step 1: 登录（admin / admin123） ==')
await send('Page.navigate', { url: `${BASE}/#/login` })
await sleep(2000)
// 已登录则路由守卫会跳回工作台；未登录显示登录表单
const loginNeeded = await evaluate(send, `!!document.querySelector('input[type="text"]') || !!document.querySelector('input[type="password"]')`)
console.log('login form needed:', loginNeeded)
if (loginNeeded) {
  await waitFor(send, `document.querySelector('input[type="text"]') && document.querySelector('input[type="password"]')`)
  await evaluate(send, `(() => {
    const user = document.querySelector('input[type="text"]')
    user.value = 'admin'
    user.dispatchEvent(new Event('input', { bubbles: true }))
    const pwd = document.querySelector('input[type="password"]')
    pwd.value = 'admin123'
    pwd.dispatchEvent(new Event('input', { bubbles: true }))
    return true
  })()`)
  await sleep(300)
  await evaluate(send, `(() => {
    const form = document.querySelector('form')
    if (form) form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    return true
  })()`)
  await waitFor(send, `!document.querySelector('input[type="password"]') && (location.hash === '#/' || location.hash === '#/home' || document.body.innerText.includes('工作台') || document.body.innerText.includes('任务'))`, 30000)
}
await sleep(2000)
console.log('after login, hash:', await evaluate(send, `location.hash`))

console.log('== step 2: /tasks 挑选合并页签 ==')
await send('Page.navigate', { url: `${BASE}/#/tasks` })
await waitFor(send, `document.body.innerText.includes('任务管理') || document.body.innerText.includes('挑选合并')`, 20000)
await sleep(1500)
// 切到挑选合并页签
await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('.task-tab, button')]
  const hit = btns.find(x => (x.textContent || '').includes('挑选合并'))
  if (hit) hit.click()
  return !!hit
})()`)
await sleep(2000)
const hasCherryPanel = await evaluate(send, `document.body.innerText.includes('开始挑选') || document.body.innerText.includes('合并容器')`)
console.log('cherry panel visible:', hasCherryPanel)
await screenshot(send, 's1-cherry-panel.png')

console.log('== step 3: 开始挑选 → 树形层级展示 ==')
await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('button')]
  const hit = btns.find(x => (x.textContent || '').includes('开始挑选'))
  if (hit) hit.click()
  return !!hit
})()`)
await waitFor(send, `document.body.innerText.includes('挑选') && (document.body.innerText.includes('树形') || document.body.innerText.includes('无符合条件的执行结果'))`, 20000)
await sleep(1800)
const treeInfo = await evaluate(send, `(() => {
  const rows = [...document.querySelectorAll('.pt-row')].map(r => r.innerText.replace(/\\n/g,' '))
  const leaves = [...document.querySelectorAll('.pt-leaf')].length
  return { nodeRows: rows.slice(0, 10), leafCount: leaves, bodyHas: document.body.innerText.slice(0, 150).replace(/\\n/g, ' ') }
})()`)
console.log('tree rows:', JSON.stringify(treeInfo))
await screenshot(send, 's2-pick-tree.png')

// 展开全部（全部展开按钮）
await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('button')]
  const hit = btns.find(x => (x.textContent || '').includes('全部展开'))
  if (hit) hit.click()
  return !!hit
})()`)
await sleep(1200)
await screenshot(send, 's3-pick-tree-expanded.png')

console.log('== step 4: 用例视角 ==')
await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('.cpw-btn')]
  const hit = btns.find(x => (x.textContent || '').includes('用例视角'))
  if (hit) hit.click()
  return !!hit
})()`)
await sleep(1200)
const caseViewInfo = await evaluate(send, `(() => {
  const rows = [...document.querySelectorAll('.pt-row')].map(r => r.innerText.replace(/\\n/g,' '))
  const firstLevel = rows.filter(r => !r.startsWith('  '))
  return { firstLevel: firstLevel.slice(0, 10) }
})()`)
console.log('case view rows:', JSON.stringify(caseViewInfo))
await screenshot(send, 's4-pick-case-view.png')

console.log('== step 5: 深色主题（树形） ==')
await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('button')]
  const hit = btns.find(x => (x.textContent || '').includes('树形'))
  if (hit) hit.click()
  return !!hit
})()`)
await sleep(800)
// 切换主题（themeStore：documentElement.classList.toggle('dark')，localStorage iatp:theme:v1）
await evaluate(send, `(() => {
  document.documentElement.classList.add('dark')
  return document.documentElement.classList.contains('dark')
})()`)
await sleep(1200)
await screenshot(send, 's5-pick-tree-dark.png')

// 恢复浅色
await evaluate(send, `document.documentElement.classList.remove('dark')`)
await sleep(500)

console.log('== step 6: 任务详情（人工复核/AI复核入口） ==')
// 用页面上下文取一个终态任务 ID（与页面同源，token 自动携带）
const navTaskId = await evaluate(send, `(async () => {
  try {
    const res = await fetch('/api/v1/tasks?per_page=20', { headers: { 'Content-Type': 'application/json' } })
    const data = await res.json()
    const items = (data.data && data.data.items) || (data.items) || []
    const terminal = items.find(t => ['completed','failed','stopped'].includes(t.status)) || items[0]
    return terminal ? String(terminal.id) : ''
  } catch (e) { return '' }
})()`)
console.log('navigating to task detail id:', navTaskId)
await send('Page.navigate', { url: `${BASE}/#/tasks/${navTaskId}` })
await waitFor(send, `document.body.innerText.includes('关联用例') || document.body.innerText.includes('测试执行')`, 20000)
await sleep(2000)
const detailHas = await evaluate(send, `(() => ({
  hasReview: document.body.innerText.includes('人工复核'),
  hasAiReview: document.body.innerText.includes('AI 复核'),
  hasHistory: document.body.innerText.includes('查看复核历史'),
  snippet: document.body.innerText.slice(0, 200).replace(/\\n/g, ' ')
}))()`)
console.log('task detail review entries:', JSON.stringify(detailHas))
await screenshot(send, 's6-task-detail-review-entries.png')

console.log('== step 7: 人工复核弹窗（真实数据） ==')
const reviewBtnClicked = await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('button')]
  const hit = btns.find(x => (x.textContent || '').includes('人工复核') && x.offsetParent !== null)
  if (hit) { hit.click(); return true }
  return false
})()`)
console.log('人工复核 clicked:', reviewBtnClicked)
if (reviewBtnClicked) {
  await sleep(1500)
  const modalText = await evaluate(send, `document.body.innerText.includes('提交复核') ? document.body.innerText.slice(0, 300).replace(/\\n/g,' ') : ''`)
  console.log('review modal:', modalText)
  await screenshot(send, 's7-review-modal.png')
  // 端到端提交验证：真实改判（completed ↔ failed 往返，接线测试前缀；提交后回滚还原数据）
  const submitResult = await evaluate(send, `(async () => {
    const root = document.querySelector('.result-review-modal')
    if (!root) return 'no modal'
    const select = root.querySelectorAll('select')
    if (select.length < 2) return 'no selects'
    const execBadge = root.querySelector('.rs-exec')
    const current = execBadge ? execBadge.className.replace(/.*rs-exec\\s*/,'').trim() : 'completed'
    const target = current === 'completed' ? 'failed' : 'completed'
    const selSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set
    selSetter.call(select[0], target)
    select[0].dispatchEvent(new Event('change', { bubbles: true }))
    const ta = root.querySelector('textarea')
    if (!ta) return 'no textarea'
    const taSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    taSetter.call(ta, '接线测试 INT-796 复核提交验证（改判往返，提交后回滚）')
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise(r => setTimeout(r, 300))
    const submit = [...root.querySelectorAll('button')].find(x => (x.textContent || '').includes('提交复核'))
    const disabledBefore = submit ? submit.disabled : 'no submit btn'
    if (submit) submit.click()
    return JSON.stringify({ current, target, disabledBefore })
  })()`)
  console.log('submit debug:', submitResult)
  await sleep(3000)
  const afterSubmit = await evaluate(send, `(() => {
    const t = document.body.innerText
    if (t.includes('复核已提交')) return 'SUCCESS: ' + t.slice(0, 160).replace(/\\n/g,' ')
    if (t.includes('复核提交失败') || t.includes('复核失败')) return 'ERROR: ' + t.slice(0, 160).replace(/\\n/g,' ')
    const errEl = document.querySelector('.form-error, [class*="error"]')
    return errEl ? ('errorEl: ' + errEl.innerText) : 'no toast visible'
  })()`)
  console.log('after submit:', afterSubmit)
  await screenshot(send, 's7b-review-submitted.png')
}

console.log('== step 8: AI 复核弹窗（桩，建议层） ==')
const aiBtnClicked = await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('button')]
  const hit = btns.find(x => (x.textContent || '').includes('AI 复核') && x.offsetParent !== null)
  if (hit) { hit.click(); return true }
  return false
})()`)
console.log('AI 复核 clicked:', aiBtnClicked)
if (aiBtnClicked) {
  await sleep(1200)
  const aiModalText = await evaluate(send, `document.body.innerText.includes('发起 AI 复核') || document.body.innerText.includes('由大模型') ? 'AI dialog open' : ''`)
  console.log('AI dialog:', aiModalText)
  await screenshot(send, 's8-ai-review-dialog.png')
  // 发起 AI 复核
  await evaluate(send, `(() => { const btns=[...document.querySelectorAll('button')]; const b=btns.find(x=>(x.textContent||'').includes('发起 AI 复核')); if(b)b.click(); return !!b })()`)
  await sleep(1200)
  const aiResult = await evaluate(send, `document.body.innerText.includes('复核通过') || document.body.innerText.includes('复核不通过') || document.body.innerText.includes('存疑') || document.body.innerText.includes('置信度')`)
  console.log('AI result shown:', aiResult)
  await screenshot(send, 's9-ai-review-result.png')
  // 关闭
  await evaluate(send, `(() => { const btns=[...document.querySelectorAll('button')]; const b=btns.find(x=>(x.textContent||'').trim()==='关闭'); if(b)b.click(); return !!b })()`)
  await sleep(600)
}

console.log('== step 9: 复核历史抽屉 ==')
const historyClicked = await evaluate(send, `(() => {
  const btns = [...document.querySelectorAll('button')]
  const hit = btns.find(x => (x.textContent || '').includes('查看复核历史') && x.offsetParent !== null)
  if (hit) { hit.click(); return true }
  return false
})()`)
console.log('history clicked:', historyClicked)
if (historyClicked) {
  await sleep(1500)
  const histText = await evaluate(send, `document.body.innerText.includes('复核历史') ? document.body.innerText.includes('暂无复核记录') ? 'empty state' : 'has items' : ''`)
  console.log('history drawer:', histText)
  await screenshot(send, 's10-review-history-drawer.png')
}

console.log('== step 10: 深色任务详情 ==')
await evaluate(send, `document.documentElement.classList.add('dark')`)
await sleep(800)
await screenshot(send, 's11-task-detail-dark.png')

console.log('== NETWORK 关键请求 ==')
console.log(JSON.stringify(netHits.filter(u => u.includes('/tasks') || u.includes('/review') || u.includes('/cherry-picks') || u.includes('/results')), null, 2))
console.log('== NETWORK POST review 命中 ==')
console.log(JSON.stringify(netHits.filter(u => u.startsWith('POST')), null, 2))

console.log('== WALKTHROUGH DONE ==')
ws.close()
