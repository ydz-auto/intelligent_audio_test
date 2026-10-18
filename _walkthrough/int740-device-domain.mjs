/**
 * INT-740 设备域交付走查——设备管理(/Device→/devices) / 音频管理(/AudioImport→/audio-import) / SPL映射(/SPLMapping)
 * 隔离 Chrome CDP :9223，连本 run dev server :5501（连常驻后端 :5000，AUTH_MODE=off）。
 * 产出：每页 浅/深 两张 PNG + Network 请求汇总（HTML 渲染截图）。
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, 'shots', 'int740')
mkdirSync(OUT_DIR, { recursive: true })

const BASE = 'http://127.0.0.1:5501'
const CDP_HTTP = 'http://127.0.0.1:9223'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  // 新建一个空白页 target 专用（避免与其它残留页混用）
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
  const requests = new Set()
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
    } else if (msg.method === 'Network.requestWillBeSent') {
      const url = msg.params.request.url || ''
      if (url.includes('/api/v1/')) requests.add(url.split('/api/v1/')[1])
    }
  }
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true })).result?.value
  const waitFor = async (expr, timeoutMs = 30000) => {
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
  const nav = async (url) => {
    await send('Page.navigate', { url: `${BASE}/#${url}` })
  }

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Network.enable')

  // ===== 1. 设备管理（测试设备页签，浅色） =====
  console.log('== step 1: 设备管理（测试设备页签，浅色） ==')
  await nav('/Device')
  await waitFor(`document.body.innerText.includes('设备管理') && document.body.innerText.includes('测试设备列表')`, 30000)
  await waitFor(`!!document.querySelector('.device-card, .devices-grid') && !document.body.innerText.includes('正在加载设备列表')`, 30000)
  await sleep(2500)
  const deviceLight = await evaluate(`(() => {
    const cards = document.querySelectorAll('.device-card').length
    const labFacet = document.body.innerText.includes('实验室')
    const labOnCard = [...document.querySelectorAll('.device-card')].some(x => x.innerText.includes('未绑定'))
    return { cards, labFacet, labOnCard }
  })()`)
  console.log('device light DOM:', JSON.stringify(deviceLight))
  await screenshot('f01-device-light.png')

  // 深色
  await evaluate(`document.documentElement.classList.add('dark')`)
  await sleep(800)
  console.log('device dark toggled')
  await screenshot('f01-device-dark.png')
  await evaluate(`document.documentElement.classList.remove('dark')`)
  await sleep(400)

  // 实验室 facet 交互验证（选项为空时检查「暂无可选项」兜底）
  console.log('== step 1b: 实验室 facet 交互 ==')
  const labFacetState = await evaluate(`(() => {
    const filter = [...document.querySelectorAll('.filter-bar .badge-filter')].find(x => x.textContent.includes('实验室'))
    if (!filter) return { present: false }
    return { present: true, text: filter.innerText.replace(/\\n/g, ' ').slice(0, 60) }
  })()`)
  console.log('lab facet state:', JSON.stringify(labFacetState))

  // ===== 2. 播放设备页签（浅/深） =====
  console.log('== step 2: 设备管理（播放设备页签） ==')
  await evaluate(`(() => { const btns=[...document.querySelectorAll('.device-type-tabs .tab-btn')]; const b=btns.find(x=>x.textContent.includes('播放')); if(b){b.click();return true} return false })()`)
  await waitFor(`document.body.innerText.includes('设备列表') || document.body.innerText.includes('播放设备')`, 15000)
  await sleep(2500)
  await screenshot('f01b-playback-light.png')
  await evaluate(`document.documentElement.classList.add('dark')`)
  await sleep(600)
  await screenshot('f01b-playback-dark.png')
  await evaluate(`document.documentElement.classList.remove('dark')`)

  // ===== 3. 音频管理（浅/深） =====
  console.log('== step 3: 音频管理 ==')
  await nav('/AudioImport')
  await waitFor(`document.body.innerText.includes('音频管理') && (document.body.innerText.includes('上传音频') || document.body.innerText.includes('音频文件'))`, 30000)
  await sleep(2500)
  const audioOk = await evaluate(`({ hasUpload: document.body.innerText.includes('上传音频'), hasList: document.body.innerText.includes('列表视图') || document.body.innerText.includes('文件名'), hasFolder: document.body.innerText.includes('文件夹视图') })`)
  console.log('audio DOM:', JSON.stringify(audioOk))
  await screenshot('f02-audio-light.png')
  await evaluate(`document.documentElement.classList.add('dark')`)
  await sleep(800)
  await screenshot('f02-audio-dark.png')
  await evaluate(`document.documentElement.classList.remove('dark')`)
  await sleep(400)

  // ===== 4. SPL 映射（浅/深） =====
  console.log('== step 4: SPL 映射 ==')
  await nav('/SPLMapping')
  await waitFor(`document.body.innerText.includes('声压级映射管理') && (document.body.innerText.includes('增益映射数') || document.body.innerText.includes('映射关系列表'))`, 30000)
  await sleep(2500)
  const splOk = await evaluate(`({ hasDeviceTab: document.body.innerText.includes('设备 SPL'), hasApiTab: document.body.innerText.includes('RMS-SPL'), hasSymmetry: document.body.innerText.includes('三口径对称') })`)
  console.log('spl DOM:', JSON.stringify(splOk))
  await screenshot('f03-spl-light.png')
  await evaluate(`document.documentElement.classList.add('dark')`)
  await sleep(800)
  await screenshot('f03-spl-dark.png')
  await evaluate(`document.documentElement.classList.remove('dark')`)
  await sleep(400)

  // 数字域页签
  console.log('== step 4b: SPL 数字域页签 ==')
  await evaluate(`(() => { const btns=[...document.querySelectorAll('.spl-domain-tabs .domain-tab-btn')]; const b=btns.find(x=>x.textContent.includes('RMS-SPL')); if(b){b.click();return true} return false })()`)
  await waitFor(`document.body.innerText.includes('RMS-SPL 映射数') || document.body.innerText.includes('RMS-SPL 映射列表')`, 15000)
  await sleep(2000)
  await screenshot('f03b-spl-digital-light.png')

  // ===== 5. Network 汇总（HTML 渲染 → 截图） =====
  console.log('== step 5: Network 汇总 ==')
  const apiCalls = [...requests].sort()
  const netHtml = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:Menlo,Consolas,monospace;font-size:13px;background:#1e1e1e;color:#d4d4d4;padding:24px}
    h1{font-size:16px;color:#4ec9b0}
    .u{display:block;padding:6px 0;border-bottom:1px solid #333}
    .m{color:#569cd6;font-weight:600}
    </style></head><body><h1>INT-740 设备域 Network 请求汇总</h1>
    ${apiCalls.map(u => `<span class="u"><span class="m">/api/v1/</span>${u}</span>`).join('') || '<div>未捕获到 /api/v1 请求</div>'}
    </body></html>`
  await evaluate(`document.body.innerHTML = ${JSON.stringify(netHtml)}`)
  await sleep(800)
  await screenshot('f05-network.png')

  console.log('NETWORK_REQUESTS=' + JSON.stringify(apiCalls, null, 2))
  console.log('== INT-740 WALKTHROUGH DONE ==')
  ws.close()
}

main().catch((e) => { console.error('WALKTHROUGH FAILED:', e.message); process.exit(1) })
