/**
 * INT-622 P1 复现验证——失效 token 的 POST /auth/logout 401 循环是否根除。
 * 复现口径与测试工程师一致（真实浏览器，隔离栈 :6273，AUTH_MODE=dev）：
 *   1. 打开 http://127.0.0.1:6273/#/login
 *   2. localStorage.setItem('auth_token', 'invalid-token-zzz') 后刷新
 *   3. 观察：POST /auth/logout 应至多 1 次（或 0 次）、本地清理完成、
 *      登录页落定且 redirect 参数单层（不再无界嵌套）
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
    } else if (msg.method) {
      events.push(msg)
    }
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
  if (r.result?.exceptionDetails) throw new Error('eval failed: ' + JSON.stringify(r.result.exceptionDetails))
  return r.result?.value
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function waitFor(send, expr, timeoutMs = 30000) {
  const start = Date.now()
  for (;;) {
    const v = await evaluate(send, expr)
    if (v) return v
    if (Date.now() - start > timeoutMs) throw new Error('timeout: ' + expr)
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

console.log('== 1. 打开登录页 ==')
await send('Page.navigate', { url: `${BASE}/#/login` })
await waitFor(send, `document.querySelector('input[type="text"]') && document.querySelector('input[type="password"]')`)
await sleep(500)

console.log('== 2. 注入失效 token 并刷新 ==')
await evaluate(send, `localStorage.setItem('auth_token', 'invalid-token-zzz'); true`)
await send('Page.reload', { ignoreCache: true })
// 等登录页重新渲染
await waitFor(send, `!!document.querySelector('input[type="text"]') && !!document.querySelector('input[type="password"]')`, 30000)
// 再给 401 循环足够的观察窗口（原缺陷 5s 内 657 次）
await sleep(6000)

const logoutRequests = events.filter((m) =>
  m.method === 'Network.requestWillBeSent' &&
  (m.params?.request?.url || '').includes('/auth/logout')
)
const otherRequests = events.filter((m) =>
  m.method === 'Network.requestWillBeSent' &&
  !(m.params?.request?.url || '').includes('/auth/logout')
)

const state = await evaluate(send, `({
  hash: location.hash,
  hashLen: location.hash.length,
  token: localStorage.getItem('auth_token'),
  user: localStorage.getItem('auth_user'),
  loginInput: !!document.querySelector('input[type="text"]'),
  pwdInput: !!document.querySelector('input[type="password"]'),
  bodySnippet: document.body.innerText.slice(0, 120).replace(/\\n/g, ' ')
})`)

console.log('== 3. 结果 ==')
console.log('logout 请求数（观察窗口 ' + Math.round(logoutRequests.length) + '）:')
logoutRequests.slice(0, 5).forEach((m) => {
  console.log('  POST ' + m.params.request.url)
})
console.log('其它请求数: ' + otherRequests.length)
console.log('页面状态: ' + JSON.stringify(state))

console.log('断言:')
const asserts = {
  'logout 请求 ≤ 1': logoutRequests.length <= 1,
  'token 已清除': state.token === null,
  '登录页落定（输入框在）': state.loginInput && state.pwdInput,
  'hash 指向登录页': state.hash.startsWith('#/login'),
  'redirect 参数单层（hash 长度 < 100）': state.hashLen < 100,
}
for (const [k, v] of Object.entries(asserts)) {
  console.log(`  ${v ? 'PASS' : 'FAIL'}  ${k}`)
}

if (logoutRequests.length === 0) {
  console.log('  (0 次 = 页面在登录页未触发认证请求，亦符合验收"至多 1 次或 0 次")')
}

await screenshot(send, '07-invalid-token-401-loop-fixed.png')
console.log('== DONE ==')
ws.close()

const allPass = Object.values(asserts).every(Boolean)
process.exit(allPass ? 0 : 1)
