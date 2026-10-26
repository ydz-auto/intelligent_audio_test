/** 极小 CDP 客户端：供 INT-1983 走查脚本复用 */
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export async function connect(CDP_HTTP = 'http://127.0.0.1:9223') {
  const targets = await (await fetch(`${CDP_HTTP}/json`)).json()
  const page = targets.find((t) => t.type === 'page' && !t.url.startsWith('devtools') && !t.url.startsWith('chrome://'))
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
    } else {
      events.push(msg)
    }
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (r.exceptionDetails) throw new Error('eval error: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text))
    return r.result?.value
  }
  return { ws, send, evaluate, events }
}

export function helpers(send, evaluate) {
  const waitFor = async (expr, timeoutMs = 45000, label = '') => {
    const start = Date.now()
    for (;;) {
      let ok = false
      try { ok = await evaluate(expr) } catch { ok = false }
      if (ok) return
      if (Date.now() - start > timeoutMs) throw new Error('timeout waiting: ' + (label || expr))
      await sleep(300)
    }
  }
  const screenshot = async (outDir, name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    const file = join(outDir, name)
    writeFileSync(file, Buffer.from(r.data, 'base64'))
    console.log('[shot] ' + name)
    return file
  }
  const click = (selector, index = 0) => evaluate(`(() => {
    const els = document.querySelectorAll(${JSON.stringify(selector)});
    if (!els[${index}]) return false;
    els[${index}].click();
    return true;
  })()`)
  const setInput = (selector, value, index = 0) => evaluate(`(() => {
    const el = document.querySelectorAll(${JSON.stringify(selector)})[${index}];
    if (!el) return false;
    el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`)
  const setDark = async (on) => {
    await evaluate(`document.documentElement.classList.${on ? 'add' : 'remove'}('dark')`)
    // 主题切换后留足样式生效时间（250ms 时截到中间态）
    await sleep(1200)
  }
  return { waitFor, screenshot, click, setInput, setDark }
}

/** 读取 CDP 事件里的响应体（Network.getResponseBody 需 requestId） */
export async function readBodies(send, events, filterFn) {
  const out = []
  for (const ev of events) {
    if (ev.method !== 'Network.responseReceived') continue
    const res = ev.params.response
    if (!filterFn(res, ev.params)) continue
    try {
      const body = await send('Network.getResponseBody', { requestId: ev.params.requestId })
      out.push({ url: res.url, status: res.status, body: body.body })
    } catch { /* 请求体已被清理 */ }
  }
  return out
}
