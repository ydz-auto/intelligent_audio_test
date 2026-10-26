/** 连接指定 CDP 目标（避免与其它页面调试会话抢占同一个 target） */
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export async function connectTarget(wsUrl) {
  const ws = new WebSocket(wsUrl)
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

export async function newTab(cdpHttp = 'http://127.0.0.1:9223', url = 'about:blank') {
  const r = await fetch(`${cdpHttp}/json/new?url=${encodeURIComponent(url)}`, { method: 'PUT' })
  return (await r.json()).webSocketDebuggerUrl
}
