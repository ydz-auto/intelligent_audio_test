/**
 * INT-2025 实测走查：新增 API 弹窗（协议 × 流式性）+ 失败保留 + 成功刷新网格。
 *
 * 环境：本 run 自建 dev server http://127.0.0.1:5600（代理 → 常驻网关 127.0.0.1:15000，
 * 数据库 intelligent_audio_test），CDP 驱动本机 Chrome（9223）。
 *
 * 断言：
 *  1) 弹窗不再有「被测设备类型 / deviceType」，改为「协议」+「流式性」；
 *     协议选 websocket → 流式性自动为流式且锁定；
 *  2) 提交失败（端点非法 → 后端 400）→ 弹窗不关闭、已填内容保留；
 *  3) 提交成功（201）→ 关闭弹窗；「被测 API」网格条数即时 +1（不整页刷新），
 *     请求体带 protocol / streaming 且不含 device_type。
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, 'shots')
mkdirSync(OUT_DIR, { recursive: true })

const BASE = 'http://127.0.0.1:5600'
const CDP_HTTP = 'http://127.0.0.1:9333'
const API_NAME = '接线测试_INT2025_API'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  const target = await (await fetch(`${CDP_HTTP}/json/new?${encodeURIComponent(BASE + '/#/login')}`, { method: 'PUT' })).json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let seq = 0
  const pending = new Map()
  const events = []
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data)
    if (data.id && pending.has(data.id)) {
      const { resolve, reject } = pending.get(data.id)
      pending.delete(data.id)
      data.error ? reject(new Error(JSON.stringify(data.error))) : resolve(data.result)
    }
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
  ws.addEventListener('message', (msg) => {
    const data = JSON.parse(msg.data)
    if (data.method) events.push(data)
  })

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Network.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })

  const evaluate = async (expression, awaitPromise = true) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true })
    if (r.exceptionDetails) throw new Error(`eval failed: ${expression}\n${JSON.stringify(r.exceptionDetails)}`)
    return r.result?.value
  }
  const waitFor = async (expression, label, timeout = 30000) => {
    const start = Date.now()
    while (Date.now() - start < timeout) {
      try { if (await evaluate(expression)) return true } catch { /* page reloading */ }
      await sleep(300)
    }
    throw new Error(`超时等待: ${label} (${expression})`)
  }
  const shot = async (name) => {
    const { data } = await send('Page.captureScreenshot', { format: 'png' })
    writeFileSync(join(OUT_DIR, name), Buffer.from(data, 'base64'))
  }
  const clickText = async (selector, text) => {
    return evaluate(`(() => {
      const els = [...document.querySelectorAll(${JSON.stringify(selector)})]
      const el = els.find(e => (e.textContent || '').includes(${JSON.stringify(text)}))
      if (!el) return false
      el.click(); return true
    })()`)
  }
  const setInput = async (selector, value) => {
    return evaluate(`(() => {
      const el = document.querySelector(${JSON.stringify(selector)})
      if (!el) return false
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(value)})
      el.dispatchEvent(new Event('input', { bubbles: true }))
      el.dispatchEvent(new Event('change', { bubbles: true }))
      return true
    })()`)
  }
  const setSelect = async (selector, value) => {
    return evaluate(`(() => {
      const el = document.querySelector(${JSON.stringify(selector)})
      if (!el) return false
      el.value = ${JSON.stringify(value)}
      el.dispatchEvent(new Event('change', { bubbles: true }))
      return el.value
    })()`)
  }

  // ===== 登录（先清登录态，避免 profile 复用把 /login 重定向到工作台）=====
  await waitFor(`document.readyState === 'complete'`, '页面首载', 30000)
  await evaluate(`localStorage.removeItem('auth_token'); localStorage.removeItem('user_info'); localStorage.removeItem('iatp:theme:v1'); location.reload()`)
  await waitFor(`!!document.querySelector('input[type=password]')`, '登录页渲染')
  await setInput('input[type=text]', '接线测试_admin')
  await setInput('input[type=password]', 'JieXianTest@2026')
  await evaluate(`document.querySelector('form button[type=submit]').click()`)
  await waitFor(`!location.hash.includes('/login') && !!localStorage.getItem('auth_token')`, '登录成功', 45000)
  const loginInfo = await evaluate(`({ hash: location.hash, token: (localStorage.getItem('auth_token')||'').slice(0,12), user: localStorage.getItem('user_info') })`)

  // ===== 进入开始测试 step1（点击进度第 2 步「选择设备/API」）=====
  await evaluate(`location.hash = '#/start-test'`)
  await waitFor(`document.querySelectorAll('.progress-step').length >= 4`, '开始测试页')
  await sleep(1500)
  await evaluate(`document.querySelectorAll('.progress-step')[1].click()`)
  await waitFor(`!!document.querySelector('.resource-section')`, '步骤1 资源区')
  await sleep(2500)

  const apiSectionExpr = `(() => {
    const s = [...document.querySelectorAll('.resource-section')].find(x => (x.querySelector('h4')?.textContent || '').includes('被测 API'))
    return s || null
  })()`
  const apiCardCount = () => evaluate(`(() => { const s = ${apiSectionExpr}; return s ? s.querySelectorAll('.resource-card').length : -1 })()`)
  const apiTotalText = () => evaluate(`(() => { const s = ${apiSectionExpr}; return s ? (s.querySelector('.pagination-container')?.textContent || 'no-pagination').replace(/\\s+/g,' ') : '' })()`)

  const beforeCount = await apiCardCount()
  const beforeTotal = await apiTotalText()
  await shot('01-step1-light.png')

  // ===== 打开新增 API 弹窗 =====
  await evaluate(`(() => { const s = ${apiSectionExpr}; const b = [...s.querySelectorAll('button')].find(x => (x.textContent||'').includes('新增API')); b.click() })()`)
  await waitFor(`!!document.querySelector('.crud-form-modal')`, '新增 API 弹窗')
  await sleep(800)

  const fieldKeys = await evaluate(`[...document.querySelectorAll('.crud-form-modal [id^="field-"]')].map(e => e.id)`)
  const hasDeviceTypeField = await evaluate(`[...document.querySelectorAll('.crud-form-modal label')].some(l => (l.textContent||'').includes('被测设备类型'))`)
  const protocolOptions = await evaluate(`(() => { const el = document.querySelector('#field-protocol'); return el ? [...el.options].map(o=>o.value) : null })()`)
  await evaluate(`document.querySelector('#field-protocol')?.scrollIntoView({ block: 'center' })`)
  await sleep(300)
  await shot('02-modal-api-light.png')

  // ===== 协议联动：选 websocket → 流式性自动流式 + 锁定 =====
  await setSelect('#field-protocol', 'websocket')
  await sleep(400)
  const wsLink = await evaluate(`(() => {
    const radios = [...document.querySelectorAll('input[name="field-streaming"]')]
    const checked = radios.find(r => r.checked)
    return { checked: checked ? checked.value : null, allDisabled: radios.every(r => r.disabled) }
  })()`)
  await evaluate(`document.querySelector('#field-streaming-true')?.scrollIntoView({ block: 'center' })`)
  await sleep(300)
  await shot('03-modal-websocket-lock-light.png')
  await setSelect('#field-protocol', 'http')
  await sleep(300)
  const httpLink = await evaluate(`(() => {
    const radios = [...document.querySelectorAll('input[name="field-streaming"]')]
    const checked = radios.find(r => r.checked)
    return { checked: checked ? checked.value : null, allDisabled: radios.every(r => r.disabled) }
  })()`)

  // ===== 失败保留：端点填非法值 → 后端 400 =====
  const netMark = events.length
  await setInput('#field-name', API_NAME)
  await setInput('#field-endpoints-0-url', 'abc')
  await sleep(300)
  await evaluate(`document.querySelector('.crud-form-modal form').requestSubmit()`)
  await sleep(2500)

  const failed = await evaluate(`(() => {
    const modal = document.querySelector('.crud-form-modal')
    return {
      modalOpen: !!modal,
      nameKept: document.querySelector('#field-name')?.value || '',
      endpointKept: document.querySelector('#field-endpoints-0-url')?.value || '',
      toast: [...document.querySelectorAll('.notification, .toast, [class*="notification"]')].map(e => (e.textContent||'').trim()).filter(Boolean).slice(-4),
    }
  })()`)
  await evaluate(`document.querySelector('#field-endpoints-0-url')?.scrollIntoView({ block: 'center' })`)
  await sleep(300)
  await shot('04-modal-submit-failed-retained-light.png')
  await evaluate(`document.querySelector('#field-name')?.scrollIntoView({ block: 'start' })`)
  await sleep(300)
  await shot('04b-modal-failed-name-kept-light.png')

  // ===== 成功：修正端点 → 201，网格即时 +1（不刷新页面）=====
  const netMark2 = events.length
  await setInput('#field-endpoints-0-url', 'http://127.0.0.1:15000/health')
  await sleep(300)
  const submitAt = Date.now()
  await evaluate(`document.querySelector('.crud-form-modal form').requestSubmit()`)

  let modalClosedMs = null
  let gridReadyMs = null
  while (Date.now() - submitAt < 30000) {
    const state = await evaluate(`(() => ({
      modalOpen: !!document.querySelector('.crud-form-modal'),
      count: (() => { const s = ${apiSectionExpr}; return s ? s.querySelectorAll('.resource-card').length : -1 })(),
    }))()`)
    if (!state.modalOpen && modalClosedMs === null) modalClosedMs = Date.now() - submitAt
    if (state.count === beforeCount + 1) { gridReadyMs = Date.now() - submitAt; break }
    await sleep(250)
  }
  await sleep(300)

  const afterCreate = await evaluate(`(() => ({
    modalOpen: !!document.querySelector('.crud-form-modal'),
    hash: location.hash,
  }))()`)
  const afterCount = await apiCardCount()
  const afterTotal = await apiTotalText()
  const gridNames = await evaluate(`(() => { const s = ${apiSectionExpr}; return s ? [...s.querySelectorAll('.card-name')].map(e=>e.textContent.trim()) : [] })()`)
  // 等上一次失败 toast 自然消失后再截「刷新后网格」，避免误读为成功仍报错
  for (let i = 0; i < 40; i++) {
    const toastVisible = await evaluate(`[...document.querySelectorAll('*')].some(e => (e.textContent || '').trim() === '提交失败')`)
    if (!toastVisible) break
    await sleep(250)
  }
  await evaluate(`(() => { const s = ${apiSectionExpr}; s && s.scrollIntoView({ block: 'start' }) })()`)
  await sleep(400)
  await shot('05-step1-grid-refreshed-light.png')

  // ===== 后端回读（GET /apis，独立于页面）=====
  const readBack = await evaluate(`(async () => {
    const t = localStorage.getItem('auth_token')
    const r = await fetch('/api/v1/apis?page=1&per_page=100', { headers: { Authorization: 'Bearer ' + t } })
    const j = await r.json()
    const items = j?.data?.items || j?.items || j?.data || []
    const hit = (Array.isArray(items) ? items : []).find(x => x.name === ${JSON.stringify(API_NAME)})
    return { status: r.status, total: j?.data?.total ?? j?.total ?? null, hit: hit ? { id: hit.id, protocol: hit.protocol, streaming: hit.streaming, device_type: hit.device_type } : null }
  })()`)

  // ===== 网络证据：POST /api/v1/apis 两次（400 / 201）=====
  const pickPosts = (fromIndex, toIndex) => events
    .filter((e, i) => i >= fromIndex && i < toIndex && e.method === 'Network.requestWillBeSent' && /\/api\/v1\/apis(\?|$)/.test(e.params.request.url) && e.params.request.method === 'POST')
    .map(e => ({ requestId: e.params.requestId, url: e.params.request.url, postData: e.params.request.postData }))
  const requests = [...pickPosts(netMark, netMark2), ...pickPosts(netMark2, events.length)]
  const responses = events
    .filter(e => e.method === 'Network.responseReceived' && /\/api\/v1\/apis(\?|$)/.test(e.params.response.url) && e.params.response.status !== 0)
    .map(e => ({ requestId: e.params.requestId, status: e.params.response.status, url: e.params.response.url }))
  const bodies = []
  for (const req of requests) {
    const resp = responses.find(r => r.requestId === req.requestId)
    let body = null
    try {
      const b = await send('Network.getResponseBody', { requestId: req.requestId })
      body = (b.base64 ? Buffer.from(b.body, 'base64').toString('utf8') : b.body)
    } catch { /* body 可能已释放 */ }
    bodies.push({ url: req.url, status: resp?.status ?? null, postData: req.postData ? JSON.parse(req.postData) : null, responseBody: body })
  }

  // ===== 深色主题截图（弹窗 + 网格）=====
  await evaluate(`localStorage.setItem('iatp:theme:v1','dark'); location.reload()`)
  await waitFor(`document.documentElement.classList.contains('dark')`, '深色主题', 20000)
  await sleep(2000)
  await evaluate(`document.querySelectorAll('.progress-step')[1]?.click()`)
  await sleep(1800)
  await evaluate(`(() => { const s = ${apiSectionExpr}; s && s.scrollIntoView({ block: 'start' }) })()`)
  await sleep(400)
  await shot('06-step1-grid-dark.png')
  await evaluate(`(() => { const s = ${apiSectionExpr}; const b = s && [...s.querySelectorAll('button')].find(x => (x.textContent||'').includes('新增API')); b && b.click() })()`)
  await waitFor(`!!document.querySelector('.crud-form-modal')`, '深色弹窗')
  await sleep(600)
  await evaluate(`document.querySelector('#field-protocol')?.scrollIntoView({ block: 'center' })`)
  await sleep(300)
  await shot('07-modal-api-dark.png')
  await evaluate(`document.querySelector('.crud-form-modal') && (document.querySelector('.crud-form-modal').closest('.modal-overlay')?.querySelector('.modal-close, .close-btn, [aria-label="关闭"]')?.click())`)

  // ===== 清理：删除本次自建 API =====
  const cleanup = await evaluate(`(async () => {
    if (!${JSON.stringify(API_NAME)}) return null
    const t = localStorage.getItem('auth_token')
    const r = await fetch('/api/v1/apis?page=1&per_page=100', { headers: { Authorization: 'Bearer ' + t } })
    const j = await r.json()
    const items = j?.data?.items || j?.items || j?.data || []
    const hit = (Array.isArray(items) ? items : []).find(x => x.name === ${JSON.stringify(API_NAME)})
    if (!hit) return { deleted: false, reason: 'not-found' }
    const d = await fetch('/api/v1/apis/' + hit.id, { method: 'DELETE', headers: { Authorization: 'Bearer ' + t } })
    return { deleted: d.ok || d.status === 204, status: d.status, id: hit.id }
  })()`)

  const result = {
    base: BASE,
    loginInfo,
    fieldKeys,
    hasDeviceTypeField,
    protocolOptions,
    wsLink,
    httpLink,
    beforeCount,
    beforeTotal,
    failed,
    afterCreate,
    modalClosedMs,
    gridReadyMs,
    afterCount,
    afterTotal,
    gridNames,
    readBack,
    requests: bodies,
    cleanup,
  }
  writeFileSync(join(OUT_DIR, 'evidence.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
  ws.close()
}

main().catch((e) => { console.error(e); process.exit(1) })
