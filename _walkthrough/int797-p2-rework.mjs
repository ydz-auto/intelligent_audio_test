/**
 * INT-797 返工走查——4×P2 修复实机验证（报告详情 人工复核 + AI 复核）
 * 连 dev server :5577（常驻后端 :5000，AUTH_MODE=off），Chrome CDP :9223。
 * 验证：
 *   P2-1 复核状态筛选与分页对齐（已复核视图：列表/总数/页数随筛选）
 *   P2-2 AI 复核「采纳」预填人工复核弹窗（评估状态 + AI 理由备注）
 *   P2-3 用例卡片 Badge 无计数只显「含复核」
 *   P2-4 取消复核弹窗不产生控制台错误（人工复核 / 采纳 AI 复核）
 * 产出：浅/深 + 筛选 + AI 结论 + 采纳预填 + 取消无错截图 + Network/控制台汇总。
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, 'shots', 'int797-p2')
mkdirSync(OUT_DIR, { recursive: true })

const BASE = 'http://127.0.0.1:5577'
const CDP_HTTP = 'http://127.0.0.1:9223'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
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
  const apiCalls = new Set()
  const consoleErrors = []
  const runtimeExceptions = []
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
    } else if (msg.method === 'Network.requestWillBeSent') {
      const url = msg.params.request.url || ''
      if (url.includes('/api/v1/')) apiCalls.add(url.split('/api/v1/')[1])
    } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
      const text = (msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ')
      consoleErrors.push(text)
    } else if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails
      runtimeExceptions.push(d?.text + ' ' + (d?.exception?.description ?? ''))
    }
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true })).result?.value
  const waitFor = async (expr, timeoutMs = 45000) => {
    const start = Date.now()
    for (;;) {
      if (await evaluate(expr)) return
      if (Date.now() - start > timeoutMs) throw new Error('timeout waiting: ' + expr)
      await sleep(350)
    }
  }
  const screenshot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    const file = join(OUT_DIR, name)
    writeFileSync(file, Buffer.from(r.data, 'base64'))
    console.log('[shot] ' + name)
    return file
  }
  const nav = async (url) => {
    await send('Page.navigate', { url: `${BASE}/#${url}` })
  }
  const setDark = async (on) => {
    await evaluate(`document.documentElement.classList.${on ? 'add' : 'remove'}('dark')`)
    await sleep(900)
  }
  // 点击匹配文本的按钮/元素
  const clickByText = async (selectorExpr, text) => {
    return evaluate(`(() => {
      const els = [...document.querySelectorAll(${JSON.stringify(selectorExpr)})]
      const el = els.find((x) => (x.innerText || '').trim().includes(${JSON.stringify(text)}))
      if (!el) return false
      el.click(); return true
    })()`)
  }

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Network.enable')
  await send('Log.enable')

  // ===== 0. 进入报告 420 =====
  console.log('== step 0: 进入报告 420 ==')
  await nav('/report/420')
  await waitFor(`document.body.innerText.includes('具体用例') || document.querySelector('.case-card') !== null`, 60000)
  await waitFor(`document.querySelectorAll('.case-card').length >= 1`, 60000)
  await waitFor(`(document.querySelector('.report-review-stats') !== null || document.querySelector('.case-review-badge') !== null)`, 60000)
  await sleep(3000)
  const summary0 = await evaluate(`(() => ({
    url: location.hash,
    hasReportHeader: !!document.querySelector('.report-review-stats'),
    headerText: document.querySelector('.report-review-stats')?.innerText?.trim() || null,
    caseCount: document.querySelectorAll('.case-card').length,
    badgeCount: document.querySelectorAll('.case-review-badge').length,
    paginationText: document.querySelector('.specific-case-pagination')?.innerText?.replace(/\\s+/g,' ').trim() || null,
    reviewFilterActive: [...document.querySelectorAll('.review-filter-option')].filter(x=>x.classList.contains('active')).map(x=>x.innerText.trim()),
  }))()`)
  console.log('summary0:', JSON.stringify(summary0))
  await screenshot('p2-00-report-light.png')

  // ===== P2-3：Badge 无计数只显「含复核」 =====
  console.log('== P2-3: 用例卡片 Badge 语义 ==')
  const badgeInfo = await evaluate(`(() => {
    const badges = [...document.querySelectorAll('.case-review-badge')]
    return {
      count: badges.length,
      texts: badges.slice(0, 4).map((b) => b.innerText.trim()),
      hasNumberCount: badges.some((b) => /已复核 \\d+/.test(b.innerText)),
      hasPrefixCount: badges.some((b) => /人工复核 \\d+/.test(b.innerText)),
    }
  })()`)
  console.log('badgeInfo:', JSON.stringify(badgeInfo))

  // ===== P2-1：复核状态筛选与分页 =====
  console.log('== P2-1: 已复核筛选 + 分页对齐 ==')
  await clickByText('.review-filter-option', '已复核')
  await waitFor(`([...document.querySelectorAll('.review-filter-option')].find(x=>x.classList.contains('active') && x.innerText.includes('已复核'))) !== undefined`, 10000)
  // 等待全量用例分批拉取 + 客户端过滤后分页更新（过滤后总计应远小于未过滤 387）
  await waitFor(`(() => {
    const p = document.querySelector('.specific-case-pagination')
    if (!p) return false
    const t = p.innerText || ''
    const m = t.match(/总计\\s*(\\d+)/)
    return m && Number(m[1]) < 100
  })()`, 60000)
  await sleep(2500)
  const filtered = await evaluate(`(() => ({
    paginationText: document.querySelector('.specific-case-pagination')?.innerText?.replace(/\\s+/g,' ').trim() || null,
    caseCount: document.querySelectorAll('.case-card').length,
    reviewedCardNames: [...document.querySelectorAll('.case-card')].slice(0, 6).map((c) => (c.querySelector('.case-name')?.innerText || '').trim().slice(0, 30)),
    activeFilter: [...document.querySelectorAll('.review-filter-option')].filter(x=>x.classList.contains('active')).map(x=>x.innerText.trim()),
  }))()`)
  console.log('filtered:', JSON.stringify(filtered))
  await screenshot('p2-01-filter-reviewed.png')

  // 回到全部
  await clickByText('.review-filter-option', '全部')
  await sleep(2000)

  // ===== P2-2 + P2-4：AI 复核发起 → 采纳预填 → 取消无错 =====
  console.log('== P2-2/4: AI 复核 采纳预填 + 取消 ==')
  const aiClick = await evaluate(`(() => {
    const btns = [...document.querySelectorAll('.review-ai-btn')]
    if (!btns.length) return { ok: false, reason: 'no ai button' }
    btns[0].click()
    return { ok: true }
  })()`)
  console.log('aiClick:', JSON.stringify(aiClick))
  if (aiClick.ok) {
    await waitFor(`document.querySelector('.ai-review-dialog') !== null`, 15000)
    const dialog0 = await evaluate(`(() => ({
      phaseText: document.querySelector('.ai-review-dialog')?.innerText?.replace(/\\s+/g,' ').trim().slice(0, 120) || '',
      hasInitiate: [...document.querySelectorAll('.ai-review-dialog button')].some((b) => b.innerText.includes('发起 AI 复核')),
    }))()`)
    console.log('ai dialog idle:', JSON.stringify(dialog0))
    await screenshot('p2-02-ai-dialog-idle.png')

    // 发起
    await clickByText('.ai-review-dialog button', '发起 AI 复核')
    await waitFor(`(document.querySelector('.ai-review-dialog')?.innerText || '').includes('复核通过') || (document.querySelector('.ai-review-dialog')?.innerText || '').includes('置信度')`, 45000)
    await sleep(1200)
    const concl = await evaluate(`(() => ({
      text: document.querySelector('.ai-review-dialog')?.innerText?.replace(/\\s+/g,' ').trim().slice(0, 220) || '',
      hasAdopt: [...document.querySelectorAll('.ai-review-dialog button')].some((b) => b.innerText.includes('采纳为复核结果')),
      hasReject: [...document.querySelectorAll('.ai-review-dialog button')].some((b) => b.innerText.trim() === '驳回'),
    }))()`)
    console.log('ai conclusion:', JSON.stringify(concl))
    await screenshot('p2-03-ai-conclusion.png')

    // 采纳 → 打开人工复核弹窗（应预填评估状态 + AI 理由）
    await clickByText('.ai-review-dialog button', '采纳为复核结果')
    await waitFor(`document.querySelector('.result-review-modal') !== null`, 15000)
    await sleep(800)
    const prefill = await evaluate(`(() => {
      const m = document.querySelector('.result-review-modal')
      const selects = [...m.querySelectorAll('select.form-select')]
      const ta = m.querySelector('textarea.form-textarea')
      return {
        title: m.querySelector('.modal-body') ? null : null,
        evalValue: selects[1]?.value ?? null,
        evalText: selects[1]?.selectedOptions?.[0]?.innerText?.trim() ?? null,
        execValue: selects[0]?.value ?? null,
        comment: ta?.value ?? null,
        bodyText: m.innerText.replace(/\\s+/g,' ').trim().slice(0, 160),
      }
    })()`)
    console.log('prefill:', JSON.stringify(prefill))
    await screenshot('p2-04-adopt-prefilled-modal.png')

    // P2-4：取消 → 不应产生 采纳 AI 复核失败 / 人工复核失败 错误
    const errCountBefore = consoleErrors.length
    await clickByText('.result-review-modal button', '取消')
    await waitFor(`document.querySelector('.result-review-modal') === null`, 10000)
    await sleep(600)
    const errAfterCancel = consoleErrors.slice(errCountBefore)
    console.log('cancel ai-adopt errs:', JSON.stringify(errAfterCancel))
  } else {
    console.log('no AI button — skip P2-2/P2-4-ai')
  }

  // ===== P2-4：人工复核弹窗取消 =====
  console.log('== P2-4: 人工复核 取消 ==')
  const manualClick = await evaluate(`(() => {
    const btns = [...document.querySelectorAll('.review-manual-btn')]
    if (!btns.length) return { ok: false, reason: 'no manual button' }
    btns[0].click()
    return { ok: true }
  })()`)
  console.log('manualClick:', JSON.stringify(manualClick))
  if (manualClick.ok) {
    await waitFor(`document.querySelector('.result-review-modal') !== null`, 30000)
    await sleep(800)
    await screenshot('p2-05-manual-modal.png')
    const errCountBefore2 = consoleErrors.length
    await clickByText('.result-review-modal button', '取消')
    await waitFor(`document.querySelector('.result-review-modal') === null`, 10000)
    await sleep(600)
    const errAfterCancel2 = consoleErrors.slice(errCountBefore2)
    console.log('cancel manual errs:', JSON.stringify(errAfterCancel2))
  } else {
    console.log('no manual button — skip P2-4-manual')
  }

  // ===== 深色 =====
  console.log('== dark ==')
  await nav('/report/420')
  await waitFor(`document.querySelectorAll('.case-card').length >= 1`, 60000)
  await sleep(3000)
  await setDark(true)
  await screenshot('p2-06-report-dark.png')
  await clickByText('.review-filter-option', '已复核')
  await sleep(3000)
  await screenshot('p2-07-filter-reviewed-dark.png')
  await setDark(false)

  // ===== 汇总 =====
  const summary = await evaluate(`(() => {
    const p = document.querySelector('.specific-case-pagination')
    return {
      finalPagination: p?.innerText?.replace(/\\s+/g,' ').trim() || null,
    }
  })()`)
  console.log('finalSummary:', JSON.stringify(summary))
  console.log('apiCalls:', JSON.stringify([...apiCalls].sort()))
  console.log('consoleErrors(all):', JSON.stringify(consoleErrors, null, 1))
  console.log('runtimeExceptions:', JSON.stringify(runtimeExceptions, null, 1))

  // 关闭标签页
  await fetch(`${CDP_HTTP}/json/close/${page.id}`, { method: 'PUT' }).catch(() => null)
  ws.close()
}

main().catch((e) => { console.error('WALKTHROUGH FAILED:', e); process.exit(1) })
