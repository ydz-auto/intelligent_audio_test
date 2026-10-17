/**
 * INT-622 登出流程回归（有效 token 点击侧栏登出）：
 * 侧栏默认收起（sidebarCollapsed=true），需先展开再点 .logout-btn。
 * 期望：POST /auth/logout → 本地清理 → 回登录页。
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, 'shots')
mkdirSync(OUT_DIR, { recursive: true })

const BASE = 'http://127.0.0.1:6374'
const CDP_HTTP = 'http://127.0.0.1:9222'

async function connect() {
  const list = await (await fetch(`${CDP_HTTP}/json`)).json()
  const page = list.find((t) => t.type === 'page')
  if (!page) throw new Error('no page target')
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let seq = 0
  const pending = new Map()
  const events = []
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
    } else if (msg.method) events.push(msg)
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
  return { ws, send, events }
}
async function evaluate(send, expression) {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true })
  return r.result?.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function waitFor(send, expr, timeoutMs = 20000) {
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
}

const { ws, send, events } = await connect()
await send('Page.enable')
await send('Runtime.enable')
await send('Network.enable')

// 确保已登录态（走查已在 step3 登录；若 token 丢了则重新登录）
let token = await evaluate(send, `localStorage.getItem('auth_token')`)
console.log('pre-state token present:', !!token)

if (!token) {
  console.log('== 重新登录（admin/admin123） ==')
  await send('Page.navigate', { url: `${BASE}/#/login` })
  await waitFor(send, `document.querySelector('input[type="text"]') && document.querySelector('input[type="password"]')`, 20000)
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
  await evaluate(send, `(() => { const form = document.querySelector('form'); form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); return true })()`)
  await waitFor(send, `location.hash === '#/' && !!localStorage.getItem('auth_token')`, 30000)
  await sleep(1500)
  token = await evaluate(send, `localStorage.getItem('auth_token')`)
  console.log('re-login token present:', !!token)
}

console.log('== 回个人中心（非首页，登出后守卫可重定向） ==')
await send('Page.navigate', { url: `${BASE}/#/AccountSettings` })
await waitFor(send, `document.body.innerText.includes('账号设置')`, 20000)
await sleep(1500)
// 触发侧栏 hover 展开（aside.sidebar 有 mouseenter 监听）
await evaluate(send, `(() => {
  const aside = document.querySelector('aside.sidebar')
  if (aside) { aside.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true })); return true }
  return false
})()`)
await waitFor(send, `!!document.querySelector('.sidebar-footer .logout-btn')`, 10000)
await sleep(500)

console.log('== 点击登出（.logout-btn） ==')
await evaluate(send, `(() => {
  const btn = document.querySelector('.logout-btn')
  if (btn) { btn.click(); return true }
  return false
})()`)
// 等回登录页
await waitFor(send, `location.hash.startsWith('#/login') || (!!document.querySelector('input[type="text"]') && location.hash.startsWith('#/login'))`, 15000)
await sleep(1200)

const logoutReqCount = events.filter((m) =>
  m.method === 'Network.requestWillBeSent' &&
  (m.params?.request?.url || '').includes('/auth/logout')
).length
const state = await evaluate(send, `({
  hash: location.hash,
  token: localStorage.getItem('auth_token'),
  user: localStorage.getItem('auth_user'),
  loginInput: !!document.querySelector('input[type="text"]'),
  bodySnippet: document.body.innerText.slice(0, 80).replace(/\\n/g, ' ')
})`)
console.log('logout POST 请求数:', logoutReqCount)
console.log('登出后状态:', JSON.stringify(state))

const asserts = {
  'POST /auth/logout 已发出': logoutReqCount >= 1,
  'token 已清除': state.token === null,
  'user 已清除': state.user === null,
  '回登录页': state.hash.startsWith('#/login') && state.loginInput,
}
for (const [k, v] of Object.entries(asserts)) console.log(`  ${v ? 'PASS' : 'FAIL'}  ${k}`)
await screenshot(send, 'r6-after-logout.png')
console.log('== DONE ==')
ws.close()
process.exit(Object.values(asserts).every(Boolean) ? 0 : 1)
