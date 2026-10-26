/**
 * INT-1983 走查 W1：B1 / B2 / B6 —— 「标签来源」三选一可见、默认两者都要、两弹窗不串值
 * 产出：上传弹窗（浅/深）、文件夹导入弹窗（浅/深）、切来源与清空标签互不影响
 */
import { connect, helpers, sleep } from './cdp.mjs'
import { mkdirSync } from 'node:fs'

const BASE = 'http://127.0.0.1:5650'
const OUT = './_walkthrough/int1983/shots'
mkdirSync(OUT, { recursive: true })

const { send, evaluate } = await connect()
const { waitFor, screenshot, setDark } = helpers(send, evaluate)
await send('Runtime.enable')
await send('Page.enable')

const log = (...a) => console.error(...a)

// 只认最上层弹窗（.modal-overlay 按 z-index 递增堆叠）
const TOP = `[...document.querySelectorAll('.modal-overlay')].slice(-1)[0]`

const clickText = (text) => evaluate(`(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim().includes(${JSON.stringify(text)}))
  if (!b) return false; b.click(); return true
})()`)

const overlayCount = () => evaluate(`document.querySelectorAll('.modal-overlay').length`)

const openUploadModal = async () => {
  const before = await overlayCount()
  await clickText('上传音频')
  await waitFor(`document.querySelectorAll('.modal-overlay').length > ${before}`, 20000, 'upload modal')
  await waitFor(`(${TOP})?.querySelector('.upload-file-modal') && (${TOP}).innerText.includes('上传音频')`, 15000, 'upload modal content')
  await sleep(700)
}
const openFolderModal = async () => {
  const before = await overlayCount()
  await clickText('批量从文件夹导入')
  await waitFor(`document.querySelectorAll('.modal-overlay').length > ${before}`, 20000, 'folder modal')
  await waitFor(`(${TOP})?.innerText.includes('批量从文件夹导入')`, 15000, 'folder modal content')
  await sleep(1000)
}
const closeModal = async () => {
  const before = await overlayCount()
  await evaluate(`(() => { (${TOP})?.querySelector('.modal-close')?.click(); return true })()`)
  await waitFor(`document.querySelectorAll('.modal-overlay').length < ${before}`, 10000, 'modal closed').catch(() => log('[warn] 关闭后 overlay 数量未减少'))
  await sleep(400)
}
const scrollToTagSource = async () => {
  await evaluate(`(() => {
    const el = (${TOP})?.querySelector('[data-field="tagSource"]')
    if (el) el.scrollIntoView({ block: 'center' })
    return true
  })()`)
  await sleep(500)
}
const tagState = () => evaluate(`(() => {
  const f = (${TOP})?.querySelector('[data-field="tagSource"]')
  return {
    visible: !!f && f.offsetParent !== null,
    checked: f ? (f.querySelector('input:checked')?.value ?? null) : null,
    labels: f ? [...f.querySelectorAll('.radio-label')].map(x => x.innerText.trim()) : [],
    hint: f ? (f.querySelector('.option-hint')?.innerText || '') : '',
  }
})()`)
const pickTagSource = async (value) => {
  await evaluate(`(() => {
    const r = (${TOP})?.querySelector('[data-field="tagSource"] input[value="' + ${JSON.stringify(value)} + '"]')
    if (!r) return false
    r.click(); return r.checked
  })()`)
  await sleep(350)
}
const tagInputItem = `[...((${TOP})?.querySelectorAll('.option-item') || [])].find(x => (x.querySelector('label')?.innerText || '').trim() === '标签')`
const fillTags = (value) => evaluate(`(() => {
  const item = ${tagInputItem}
  const input = item?.querySelector('input[type="text"]')
  if (!input) return false
  input.value = ${JSON.stringify(value)}
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
  return true
})()`)
const readTags = () => evaluate(`(() => { const item = ${tagInputItem}; return item?.querySelector('input[type="text"]')?.value ?? null })()`)

// ── 会话准备：硬刷新，避免上一次走查残留弹窗堆叠 ──
await send('Page.navigate', { url: 'about:blank' })
await sleep(800)
await send('Page.navigate', { url: `${BASE}/#/login` })
await sleep(3000)
if (await evaluate(`!!document.querySelector('input[type="password"]')`)) {
  log('[login] 需要登录')
  await evaluate(`(() => {
    const u = document.querySelector('input[type="text"]'); u.value='admin'; u.dispatchEvent(new Event('input',{bubbles:true}))
    const p = document.querySelector('input[type="password"]'); p.value='admin123'; p.dispatchEvent(new Event('input',{bubbles:true}))
    document.querySelector('form')?.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))
    return true
  })()`)
  await sleep(4500)
}
log('[nav] audio-import, hash =', await evaluate('location.hash'))
await send('Page.navigate', { url: `${BASE}/#/audio-import` })
await sleep(1500)
await waitFor(`document.body.innerText.includes('音频管理')`, 30000, 'audio page')
await evaluate(`(() => { location.reload(); return true })()`)
await sleep(6000)
await waitFor(`document.body.innerText.includes('音频管理')`, 30000, 'audio page after reload')
log('[nav] reloaded, hash =', await evaluate('location.hash'), 'overlays =', await overlayCount())

const results = {}

// ── B1：上传弹窗 ──
await openUploadModal()
results.B1_upload_initial = await tagState()
log('[B1]', JSON.stringify(results.B1_upload_initial))
await scrollToTagSource()
await setDark(false)
await screenshot(OUT, 'B1-upload-modal-light.png')
await setDark(true)
await screenshot(OUT, 'B1-upload-modal-dark.png')
await setDark(false)

await pickTagSource('json')
results.B1_afterPickJson = await tagState()
log('[B1] after pick json:', JSON.stringify(results.B1_afterPickJson))
await closeModal()
await openUploadModal()
results.B1_reopen = await tagState()
log('[B1] reopen:', JSON.stringify(results.B1_reopen))
await closeModal()

// ── B2：文件夹导入弹窗 ──
await openFolderModal()
results.B2_folder_initial = await tagState()
log('[B2]', JSON.stringify(results.B2_folder_initial))
await scrollToTagSource()
await setDark(false)
await screenshot(OUT, 'B2-folder-modal-light.png')
await setDark(true)
await screenshot(OUT, 'B2-folder-modal-dark.png')
await setDark(false)

await pickTagSource('path')
results.B2_afterPickPath = await tagState()
await closeModal()
await openUploadModal()
results.B2_upload_after_folderPickedPath = await tagState()
log('[B2] 不串值检查:', JSON.stringify(results.B2_upload_after_folderPickedPath))

// ── B6：标签输入与标签来源互不影响 ──
log('[B6] fill 手填A:', await fillTags('手填A'))
await pickTagSource('json')
await sleep(300)
results.B6_afterSwitch = { tagsInput: await readTags(), source: (await tagState()).checked }
log('[B6] 切来源后手填保留:', JSON.stringify(results.B6_afterSwitch))
log('[B6] 清空手填:', await fillTags(''))
await sleep(300)
results.B6_cleared = { tagsInput: await readTags(), source: (await tagState()).checked }
log('[B6] 清空后来源不变:', JSON.stringify(results.B6_cleared))
await scrollToTagSource()
await screenshot(OUT, 'B6-taginput-and-tagsource.png')
await closeModal()

console.log(JSON.stringify(results, null, 2))
process.exit(0)
