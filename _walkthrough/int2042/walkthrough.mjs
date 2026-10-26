/**
 * INT-2042 走查：批量更新标注弹窗 —— 默认勾选「同步刷新关联测试用例的参考参数」
 * 提交后的结果提示（刷新已改后台执行）
 *
 * 前端：本 run 构建的 dist 挂 nginx :16179（agent/b/int-2042，VITE_AUTH_MODE=dev）
 * 后端：docker 常驻网关 :15000（真实库 intelligent_audio_test）
 *
 * 只读约束：真实音频标注一律不写。提交链路的两个请求
 *   POST /api/v1/audios/by-md5、POST /api/v1/audios/batch/annotations
 * 用 CDP Fetch 在浏览器侧应答（响应体与后端新契约一致），因此本次只验证
 * 「界面渲染新提示文案」；接口/落库行为由 pytest 单测覆盖。
 */
import { connectTarget, newTab, sleep } from './cdp.mjs'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

setTimeout(() => { console.error('HARD TIMEOUT'); process.exit(2) }, 240000)

const BASE = process.env.BASE_URL || 'http://127.0.0.1:16179'
const OUT = './_walkthrough/int2042/shots'
const DATA = resolve('./_walkthrough/int2042/data')
mkdirSync(OUT, { recursive: true })
mkdirSync(DATA, { recursive: true })

const WAV = join(DATA, 'int2042_demo.wav')
const ANN = join(DATA, 'int2042_demo.json')
writeFileSync(WAV, Buffer.from('RIFF....WAVEfmt ' + 'x'.repeat(64)))
writeFileSync(ANN, JSON.stringify({ text: '接线测试_INT2042 标注', source_language: 'zh', target_language: 'en' }))

const wsUrl = await newTab('http://127.0.0.1:9223', 'about:blank')
const { send, evaluate, events } = await connectTarget(wsUrl)
await send('Runtime.enable')
await send('Page.enable')
await send('Network.enable')

const log = (...a) => console.error(...a)
const result = { steps: [], network: [], toast: {}, modal: {} }
const TOP = "document.querySelector('.batch-annotation-overlay')"

const sleepMs = (ms) => new Promise((r) => setTimeout(r, ms))
const waitFor = async (expr, timeoutMs = 30000, label = '') => {
  const start = Date.now()
  for (;;) {
    let ok = false
    try { ok = await evaluate(expr) } catch { ok = false }
    if (ok) return true
    if (Date.now() - start > timeoutMs) throw new Error('timeout waiting: ' + (label || expr))
    await sleepMs(300)
  }
}
const setDark = async (on) => {
  await evaluate(`document.documentElement.classList.${on ? 'add' : 'remove'}('dark')`)
  await sleepMs(1200)
}
const screenshot = async (name) => {
  const r = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(join(OUT, name), Buffer.from(r.data, 'base64'))
  console.error('[shot]', name)
  return join(OUT, name)
}

/* ---------- CDP Fetch 应答（不写真实标注） ---------- */
const BATCH_BODY = {
  success: true,
  code: 200,
  message: '批量更新标注成功，更新 1 个音频，关联用例参考参数刷新已在后台执行',
  data: { updated_count: 1, failed_count: 0, refreshed_test_case_ids: [], refresh_scheduled: true },
}

let handled = 0
let evCursor = 0
let interceptionOn = false
const pump = async () => {
  if (!interceptionOn) return
  while (evCursor < events.length) {
    const ev = events[evCursor++]
    if (ev.method !== 'Fetch.requestPaused') continue
    const { requestId, request } = ev.params
    const url = request.url
    let payload = null
    if (url.includes('/audios/by-md5')) {
      let md5s = []
      try { md5s = JSON.parse(request.postData || '{}').md5_list || [] } catch { md5s = [] }
      const data = {}
      md5s.forEach((m, i) => { data[m] = { id: 900001 + i, name: 'int2042_demo.wav' } })
      payload = { success: true, code: 200, data }
    } else if (url.includes('/audios/batch/annotations')) {
      payload = BATCH_BODY
    }
    if (!payload) continue
    handled += 1
    result.steps.push({ intercepted: url.replace(BASE, ''), body: payload.data })
    await send('Fetch.fulfillRequest', {
      requestId,
      responseCode: 200,
      responseHeaders: [
        { name: 'Content-Type', value: 'application/json; charset=utf-8' },
        { name: 'Access-Control-Allow-Origin', value: '*' },
      ],
      body: Buffer.from(JSON.stringify(payload)).toString('base64'),
    })
  }
}
const pumpTimer = setInterval(() => { pump().catch((e) => log('[pump-err]', e.message)) }, 60)

try {
  /* ---------- 音频管理（复用已登录会话） ---------- */
  await send('Page.navigate', { url: `${BASE}/#/audio-import` })
  await sleepMs(2500)
  await send('Page.reload', {})
  await sleepMs(3000)
  await waitFor("document.body.innerText.includes('批量更新标注')", 90000, 'audio page')
  result.steps.push({ page: await evaluate('location.hash + " | " + document.title') })

  const clicked = await evaluate(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim() === '批量更新标注')
    if (!b) return false; b.click(); return true
  })()`)
  await waitFor(`!!${TOP}`, 20000, 'modal')
  await sleepMs(900)
  result.steps.push({ open_modal: clicked })

  /* ---------- 选文件（by-md5 走拦截应答） ---------- */
  await send('Fetch.enable', {
    patterns: [
      { urlPattern: '*audios/by-md5*', requestStage: 'Request' },
      { urlPattern: '*batch/annotations*', requestStage: 'Request' },
    ],
  })
  interceptionOn = true

  const { root } = await send('DOM.getDocument', { depth: -1 })
  const { nodeId } = await send('DOM.querySelector', { nodeId: root.nodeId, selector: '.batch-annotation-modal input[type=file]' })
  result.steps.push({ file_input_node: nodeId })
  await send('DOM.setFileInputFiles', { files: [WAV, ANN], nodeId })
  await waitFor(`(${TOP}?.querySelectorAll('.file-item').length || 0) > 0`, 30000, 'parsed items')
  await waitFor(`(() => { const b = ${TOP}?.querySelector('.modal-footer .btn-primary'); return !!b && !b.disabled })()`, 30000, 'submit enabled')
  await sleepMs(500)
  result.steps.push({ items_parsed: await evaluate(`(${TOP}?.querySelectorAll('.file-item').length || 0)`) })

  // 默认勾选状态：「同步刷新关联测试用例的参考参数」（有解析结果后才渲染）
  result.modal.checkbox_checked = await evaluate(`(() => {
    const root = ${TOP}; const cb = root?.querySelector('.checkbox-col input[type=checkbox]'); return cb ? cb.checked : null
  })()`)
  result.modal.label = await evaluate(`(${TOP}?.querySelector('.checkbox-col .checkbox-label span')?.textContent || '').trim()`)
  await setDark(false)
  result.modal.light = await screenshot('modal-default-light.png')
  await setDark(true)
  result.modal.dark = await screenshot('modal-default-dark.png')
  await setDark(false)

  /* ---------- 提交 → 结果 toast ---------- */
  await evaluate(`${TOP}.querySelector('.modal-footer .btn-primary').click()`)
  await sleepMs(1500)
  // 成功路径父组件（AudioImport.handleAnnotationSuccess）立即关窗，toast 通常不可见；
  // 这里如实记录，不伪造截图。
  result.toast.overlay_after_submit = await evaluate(`!!${TOP}`)
  result.toast.detail = await evaluate(`(${TOP}?.querySelector('.result-toast .toast-body span')?.textContent || '').trim() || ''`)
  result.steps.push({ intercepted_count: handled })
  result.modal.after_submit = await screenshot('after-submit-light.png')

  /* ---------- 请求取证 ---------- */
  for (const ev of events) {
    if (ev.method !== 'Network.requestWillBeSent') continue
    const { request } = ev.params
    if (!request.url.includes('/api/')) continue
    result.network.push({ method: request.method, url: request.url.replace(BASE, '') })
  }
  result.health = await (await fetch('http://127.0.0.1:15000/health')).json()
} catch (e) {
  result.error = e.message
  log('[FATAL]', e.message)
} finally {
  clearInterval(pumpTimer)
  try { await send('Fetch.disable') } catch { /* ignore */ }
  writeFileSync(join(OUT, 'evidence.json'), JSON.stringify(result, null, 2))
  log(JSON.stringify(result, null, 2))
  setTimeout(() => process.exit(0), 300)
}
