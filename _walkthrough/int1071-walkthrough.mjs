/**
 * INT-1071 返工走查——报告具体用例「下载日志」两段流程（文件选择 Dialog + 打包下载进度）
 *
 * 后端说明：日志文件列表端点（INT-1062）代码已 done，但集成卡 INT-1083 在途，
 * 常驻栈 :5000 尚无双端点 → 列表请求真实发出并返回 404（Phase A 截图真实错误态）。
 * Phase B 用 CDP Fetch 拦截「列表端点」响应，回填真实文件清单（取自常驻栈
 * 整包下载 zip 的实际 arcname + size，非虚构），仅用于渲染验证文件列表 UI；
 * 「下载」请求全部走真实后端（logs/download 200 真实 zip；files 缺省=整包 / ?files= 按所选）。
 *
 * P2 返工（真实进度/速度）：downloadCaseLogs 已改 fetch ReadableStream 逐块读取，按
 * Content-Length 算真实 %、500ms 采样速率。小 zip 一闪即过 → 用 CDP Network.emulateNetworkConditions
 * 把下载吞吐限到 8 KB/s（实测对 localhost 生效），进度 Dialog 中的 % / 已下载·总量 / 速度
 * 全部由真实字节流算出，截图捕获中途态即真实进度。
 *
 * 产出：浅/深色 + 文件列表 + 多选合计 + 真实进度 Dialog + Network 汇总。
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, 'shots', 'int1071')
mkdirSync(OUT_DIR, { recursive: true })

const BASE = 'http://127.0.0.1:5581'
const CDP_HTTP = 'http://127.0.0.1:9223'

const REPORT_ID = 65
const CASE_ID = '5412e6d4-be58-4446-9dc0-d40f739e919f'

// 真实文件清单：取自常驻栈整包下载 zip 的 arcname + size（2026-10-21 实测 report 65）
const REAL_FILES = [
  { name: 'api/result_data.json', size: 2019 },
  { name: 'business_logs/common/shared/execution.evaluation_service.DESKTOP-3SNNDSS-34836.log', size: 81019 },
  { name: 'business_logs/common/shared/execution.evaluation_service.DESKTOP-3SNNDSS-36640.log', size: 192659 },
  { name: 'business_logs/common/shared/execution.evaluation_service.DESKTOP-3SNNDSS-43696.log', size: 58902 },
  { name: 'business_logs/common/shared/execution.evaluation_service.DESKTOP-3SNNDSS-53868.log', size: 52882 },
  { name: 'business_logs/common/shared/execution.report_service.DESKTOP-3SNNDSS-30296.log', size: 29254 },
  { name: 'business_logs/common/shared/execution.report_service.DESKTOP-3SNNDSS-52004.log', size: 22822 },
  { name: 'business_logs/common/shared/execution.task_service.DESKTOP-3SNNDSS-24020.log', size: 139484 },
  { name: 'business_logs/common/shared/execution.task_service.DESKTOP-3SNNDSS-32988.log', size: 441 },
  { name: 'business_logs/common/shared/execution.task_service.DESKTOP-3SNNDSS-43256.log', size: 64132 },
  { name: 'business_logs/common/shared/execution.task_service.DESKTOP-3SNNDSS-49000.log', size: 12448 },
  { name: 'business_logs/common/shared/execution.task_service.DESKTOP-3SNNDSS-49992.log', size: 59248 },
]

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
  const consoleErrors = []
  const runtimeExceptions = []
  const apiCalls = []
  const downloadUrls = []
  /** 拦截状态：interceptList=列表回填真实清单；下载走真实网络（限速 8KB/s 截中途进度） */
  let interceptList = false

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
    } else if (msg.method === 'Network.requestWillBeSent') {
      const url = msg.params.request.url || ''
      if (url.includes('/api/v1/')) {
        apiCalls.push(`${msg.params.request.method} ${url.split('/api/v1/')[1]}`)
        if (/\/logs\/download/.test(url)) downloadUrls.push(url.split('/api/v1/')[1])
      }
    } else if (msg.method === 'Fetch.requestPaused') {
      handlePaused(msg.params).catch((e) => console.error('[paused] fail:', e.message))
    } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
      const text = (msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ')
      consoleErrors.push(text)
    } else if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails
      runtimeExceptions.push(d?.text + ' ' + (d?.exception?.description ?? ''))
    }
  }

  async function handlePaused({ requestId, request }) {
    const url = request.url || ''
    const isList = /\/api\/v1\/reports\/[^/]+\/cases\/[^/]+\/logs$/.test(url)
    if (interceptList && isList) {
      // 回填真实文件清单（网关响应包裹：success/code/data）
      const body = JSON.stringify({ success: true, code: 0, message: 'Success', data: { items: REAL_FILES } })
      await send('Fetch.fulfillRequest', {
        requestId,
        responseCode: 200,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
        body: Buffer.from(body, 'utf8').toString('base64'),
      })
    } else {
      await send('Fetch.continueRequest', { requestId })
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
      await sleep(300)
    }
  }
  const screenshot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' })
    const file = join(OUT_DIR, name)
    writeFileSync(file, Buffer.from(r.data, 'base64'))
    console.log('[shot] ' + name)
    return file
  }
  const nav = async (url) => { await send('Page.navigate', { url: `${BASE}/#${url}` }) }
  const click = async (selector, index = 0) => {
    await evaluate(`(() => {
      const els = document.querySelectorAll(${JSON.stringify(selector)});
      if (!els[${index}]) return false;
      els[${index}].click();
      return true;
    })()`)
  }
  const setDark = async (on) => {
    await evaluate(`document.documentElement.classList.${on ? 'add' : 'remove'}('dark')`)
    await sleep(150)
  }
  const openDialog = async () => {
    await click('.download-log-btn')
    await waitFor("!!document.querySelector('.log-file-select-dialog')")
    await sleep(300)
  }
  const closeDialog = async () => {
    await evaluate(`document.querySelector('.log-file-select-close')?.click()`)
    await sleep(250)
  }
  const summaryText = async () => await evaluate(`document.querySelector('.log-file-summary')?.innerText || ''`)
  const selectedCount = async () => await evaluate(`document.querySelectorAll('.log-file-row.selected').length`)
  const listRowCount = async () => await evaluate(`document.querySelectorAll('.log-file-row').length`)
  /** 下载限速：真实字节流按 ~8KB/s 到达，使小 zip 的进度 Dialog 有可截取的中途态（实测对 localhost 生效） */
  const setThrottle = async (bytesPerSec) => {
    if (bytesPerSec > 0) {
      await send('Network.emulateNetworkConditions', {
        offline: false, latency: 50, downloadThroughput: bytesPerSec, uploadThroughput: 4 * 1024 * 1024,
      })
    } else {
      await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 })
    }
  }

  await send('Network.enable')
  await send('Runtime.enable')
  await send('Page.enable')
  // 仅拦截「列表端点」回填真实清单（Phase B）；下载请求不拦截、走真实后端限速通道
  await send('Fetch.enable', {
    patterns: [
      { urlPattern: '*://*/api/v1/reports/*/cases/*/logs', requestStage: 'Request' },
    ],
  })
  await setThrottle(0)

  // ============ Phase A：真实后端行为（列表 404 → 错误态 + 整包下载兜底） ============
  await nav(`/report/${REPORT_ID}`)
  await waitFor("document.querySelector('.case-card') || document.querySelector('.no-data-tip')")
  await sleep(1200)
  await setDark(false)
  await screenshot('A1-report-case-list-light.png')

  await openDialog()
  // 等待真实列表请求失败进入错误态
  await waitFor("!!document.querySelector('.log-file-select-error')", 30000)
  await screenshot('A2-dialog-error-light.png')

  // 深色错误态
  await setDark(true)
  await screenshot('A3-dialog-error-dark.png')

  // 错误态整包下载兜底（真实后端 /logs/download 200 真实 zip；限速 8KB/s 截真实进度）
  await setDark(false)
  await setThrottle(8 * 1024)
  await click('.log-file-error-actions .log-file-action-btn', 1) // 下载全部日志
  await waitFor("!!document.querySelector('.download-loading-modal')", 15000)
  await sleep(1500) // 真实字节流中途：进度 % + 已下载/总量 + 速度 均由真实速率算出
  await screenshot('A4-whole-zip-progress.png')
  console.log('[A4] progress text:', await evaluate(`document.querySelector('.download-loading-modal')?.innerText || ''`))
  // 等下载完成（进度 100 / 模态消失）
  await waitFor("!document.querySelector('.download-loading-modal')", 30000)
  await setThrottle(0)
  await sleep(1200)
  await screenshot('A5-whole-zip-complete.png')

  // ============ Phase B：文件列表渲染验证（CDP 回填真实清单） ============
  interceptList = true

  await nav(`/report/${REPORT_ID}`)
  await waitFor("document.querySelector('.case-card') || document.querySelector('.no-data-tip')")
  await sleep(1000)

  // 浅色：文件列表全选态（默认全选 12 个）
  await openDialog()
  await waitFor("document.querySelectorAll('.log-file-row').length >= 2", 20000)
  await screenshot('B1-file-list-light.png')
  console.log('[B1] summary:', await summaryText(), 'selected:', await selectedCount(), 'rows:', await listRowCount())

  // 全选切换：取消全选 → 0 选中 → 按钮禁用
  await click('.log-file-toggle-all')
  await sleep(200)
  await screenshot('B2-deselect-all-light.png')
  console.log('[B2] summary:', await summaryText(), 'disabled:', await evaluate(`document.querySelector('.log-file-select-footer .btn-primary')?.disabled`))

  // 全选切换：全选 → 恢复 12 个
  await click('.log-file-toggle-all')
  await sleep(200)
  await screenshot('B3-select-all-light.png')
  console.log('[B3] summary:', await summaryText(), 'selected:', await selectedCount())

  // 多选：取消勾选 3 个文件 → 已选合计变化（9/12）
  await evaluate(`(() => {
    const rows = document.querySelectorAll('.log-file-row');
    [1, 2, 3].forEach(i => rows[i].click());
  })()`)
  await sleep(200)
  await screenshot('B4-multi-select-light.png')
  console.log('[B4] summary:', await summaryText(), 'selected:', await selectedCount())

  // 深色：文件列表
  await setDark(true)
  await screenshot('B5-file-list-dark.png')

  // 下载所选文件：?files= 真实请求 + 限速 8KB/s 截真实进度（% / 已下载·总量 / 速度）
  await setDark(false)
  await setThrottle(8 * 1024)
  await click('.log-file-select-footer .btn-primary') // 下载所选文件
  await waitFor("!!document.querySelector('.download-loading-modal')", 10000)
  await sleep(1500)
  await screenshot('B6-download-progress-selected.png')
  console.log('[B6] progress text:', await evaluate(`document.querySelector('.download-loading-modal')?.innerText || ''`))
  // 等完成
  await waitFor("!document.querySelector('.download-loading-modal')", 30000)
  await setThrottle(0)
  await sleep(800)
  await screenshot('B7-download-complete.png')

  // ============ 汇总 ============
  console.log('[network] api calls:', JSON.stringify(apiCalls, null, 2))
  console.log('[network] download urls:', JSON.stringify(downloadUrls, null, 2))
  console.log('[network] console errors (non-404):', consoleErrors.filter((e) => !e.includes('Not Found')).slice(0, 5))
  console.log('[network] runtime exceptions:', runtimeExceptions.slice(0, 5))

  ws.close()
}
main().catch((e) => { console.error('[walkthrough] FAIL:', e); process.exit(1) })
