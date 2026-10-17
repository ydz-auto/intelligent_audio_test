/**
 * INT-622 P1 修复回归走查——旧 Vue 生产 UI 受影响页（登录/注册/首页/个人中心/OAuth 提供方）。
 * 与既有 walkthrough.mjs 同构，端口改隔离栈 :6273、凭证改 admin/admin123（隔离栈自举）。
 * 修复侧重点：登出（含侧栏登出按钮）在本次改动后仍可用、登录后回首页正常。
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
  const r = await send('Runtime.evaluate', { expression, returnByValue: true })
  return r.result?.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
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

const { ws, send } = await connect()
await send('Page.enable')
await send('Runtime.enable')

console.log('== step 1: 登录页（登录 Tab） ==')
await send('Page.navigate', { url: `${BASE}/#/login` })
await waitFor(send, `document.body.innerText.includes('登 录') && document.body.innerText.includes('用户名 / 邮箱')`)
await sleep(800)
const loginTabOk = await evaluate(send, `(() => {
  const user = document.querySelector('input[type="text"]')
  const pwd = document.querySelector('input[type="password"]')
  return { user: !!user, pwd: !!pwd, title: document.title }
})()`)
console.log('login tab DOM:', JSON.stringify(loginTabOk))
await screenshot(send, 'r1-login-tab.png')

console.log('== step 2: 注册 Tab（含邮箱必填） ==')
await evaluate(send, `(() => { const btns=[...document.querySelectorAll('.tab-btn')]; const b=btns.find(x=>x.textContent.includes('注 册')); b && b.click(); return !!b })()`)
await waitFor(send, `document.body.innerText.includes('确认密码') && document.body.innerText.includes('邮箱')`)
await sleep(600)
const regTabOk = await evaluate(send, `(() => {
  const email = [...document.querySelectorAll('input')].find(i=>i.type==='email')
  return { email: !!email, hasConfirm: document.body.innerText.includes('确认密码') }
})()`)
console.log('register tab DOM:', JSON.stringify(regTabOk))
await screenshot(send, 'r2-register-tab.png')

console.log('== step 3: 真实登录（admin / admin123，加密链路） ==')
await evaluate(send, `(() => { const btns=[...document.querySelectorAll('.tab-btn')]; const b=btns.find(x=>x.textContent.includes('登 录')); b && b.click(); return !!b })()`)
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
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  return true
})()`)
await waitFor(send, `location.hash === '#/' || location.hash === '' || (document.body.innerText.includes('工作台') && !document.body.innerText.includes('请输入用户名'))`, 30000)
await sleep(2000)
const afterLogin = await evaluate(send, `({ hash: location.hash, title: document.title, hasToken: !!localStorage.getItem('auth_token'), bodySnippet: document.body.innerText.slice(0, 120).replace(/\\n/g, ' ') })`)
console.log('after login:', JSON.stringify(afterLogin))
await screenshot(send, 'r3-after-login-home.png')

console.log('== step 4: 个人中心（账号设置：用户信息 / 角色 / 第三方绑定） ==')
await send('Page.navigate', { url: `${BASE}/#/AccountSettings` })
await waitFor(send, `document.body.innerText.includes('账号设置') && document.body.innerText.includes('账号信息')`)
await sleep(1500)
const accountOk = await evaluate(send, `(() => {
  const rows=[...document.querySelectorAll('.info-row')].map(r=>r.innerText.replace(/\\n/g,' / '))
  return { rows, hasBindSection: document.body.innerText.includes('第三方账号绑定') }
})()`)
console.log('account settings DOM:', JSON.stringify(accountOk))
await screenshot(send, 'r4-account-settings.png')

console.log('== step 5: OAuth 提供方管理（admin 权限页） ==')
await send('Page.navigate', { url: `${BASE}/#/OAuthProviders` })
await waitFor(send, `document.body.innerText.includes('OAuth')`, 15000)
await sleep(1500)
const oauthOk = await evaluate(send, `(() => {
  const snippet = document.body.innerText.slice(0, 200).replace(/\\n/g, ' ')
  return { snippet }
})()`)
console.log('oauth providers DOM:', JSON.stringify(oauthOk))
await screenshot(send, 'r5-oauth-providers.png')

console.log('== step 6: 侧栏登出（POST /auth/logout → 回登录页） ==')
// 回到首页，点侧栏登出按钮
await send('Page.navigate', { url: `${BASE}/#/` })
await waitFor(send, `document.body.innerText.includes('工作台') || document.body.innerText.includes('测试用例')`, 20000)
await sleep(1200)
const logoutBtn = await evaluate(send, `(() => {
  const btns=[...document.querySelectorAll('button, [class*="logout"], [class*="user-menu"] span, [class*="avatar"]')]
  const hit = btns.find(x => /登\\s*出/.test(x.textContent || ''))
  if (hit) { hit.click(); return true }
  return false
})()`)
console.log('logout button clicked:', logoutBtn)
if (logoutBtn) {
  await waitFor(send, `location.hash.startsWith('#/login')`, 15000)
  await sleep(800)
  const afterLogout = await evaluate(send, `({
    hash: location.hash,
    token: localStorage.getItem('auth_token'),
    user: localStorage.getItem('auth_user'),
    loginInput: !!document.querySelector('input[type="text"]')
  })`)
  console.log('after logout:', JSON.stringify(afterLogout))
  await screenshot(send, 'r6-after-logout.png')
}

console.log('== WALKTHROUGH DONE ==')
ws.close()
