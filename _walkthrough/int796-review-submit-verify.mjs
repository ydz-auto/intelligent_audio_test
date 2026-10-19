/**
 * INT-796 人工复核提交成功路径验证（真实接口 + 保证回滚）。
 * 页面上下文 fetch（token 自动携带）：POST /tasks/results/review 改判 → 回滚还原。
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
  const list = await (await fetch(`${CDP_HTTP}/json`)).json()
  const page = list.find((t) => t.type === 'page' && !t.url.startsWith('devtools') && !t.url.startsWith('chrome://'))
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

const { ws, send } = await connect()
await send('Runtime.enable')

const result = await evaluate(send, `(async () => {
  const TASK = 417
  const out = { fetched: false, changed: false, reverted: false, error: null }
  try {
    // 1. 取任务第一个用例的结果
    const detailRes = await fetch('/api/v1/tasks/' + TASK, { headers: { 'Content-Type': 'application/json' } })
    const detail = await detailRes.json()
    const caseId = (detail.data && detail.data.cases && detail.data.cases[0] && detail.data.cases[0].case_id)
    if (!caseId) return { error: 'no case in task detail' }
    const resRes = await fetch('/api/v1/tasks/' + TASK + '/cases/' + caseId + '/results', { headers: { 'Content-Type': 'application/json' } })
    const resData = await resRes.json()
    const items = (resData.data && resData.data.results) || []
    if (!items.length) return { error: 'no results for case' }
    const first = items[0]
    const rid = first.id
    const current = first.execution_status || 'completed'
    const target = current === 'completed' ? 'failed' : 'completed'
    out.fetched = true

    // 2. 改判（真实提交，接线测试前缀）
    const chgRes = await fetch('/api/v1/tasks/results/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_ids: [rid], execution_status: target, comment: '接线测试 INT-796 改判验证（提交后回滚）' }),
    })
    const chg = await chgRes.json()
    out.changed = chg.success === true && (chg.data?.reviewed?.length === 1 || chg.data?.review_count === 1)
    out.changeResp = { success: chg.success, message: chg.message }

    // 3. 回滚到原值（再次提交，还原数据）
    const revRes = await fetch('/api/v1/tasks/results/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_ids: [rid], execution_status: current, comment: '接线测试 INT-796 回滚还原' }),
    })
    const rev = await revRes.json()
    out.reverted = rev.success === true
    out.revertResp = { success: rev.success, message: rev.message }
    out.resultId = rid
    out.current = current
    out.target = target
  } catch (e) {
    out.error = String(e && e.message || e)
  }
  return out
})()`)

console.log('API review change+revert result:', JSON.stringify(result, null, 2))
ws.close()
