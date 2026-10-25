/**
 * INT-1777：API 编辑弹窗请求模板 / audio_config 草稿模型单测。
 * 锁定母卡 §3.1 的 meta 合并规则（base 保留未知键、清空删键、隐藏组不删）
 * 与 audio_config 顶层列四项口径。
 */
import { describe, expect, it } from 'vitest'

import {
  audioConfigDraftFrom,
  buildAudioConfig,
  deriveDraftTargetDeviceType,
  mergeRequestTemplateMeta,
  newKeyValueRow,
  requestTemplateDraftFromMeta,
} from '../api-edit-dialog-model'

describe('requestTemplateDraftFromMeta 编辑态回填', () => {
  it('对象 body_template → 结构化 JSON 模式；字符串 → 原始模板模式', () => {
    const jsonDraft = requestTemplateDraftFromMeta({
      method: 'POST',
      body_template: { text: '{{text}}' },
      headers: { 'Content-Type': 'application/json' },
      vendor_adapter: 'OpenAIAdapter',
    })
    expect(jsonDraft.method).toBe('POST')
    expect(jsonDraft.bodyTemplateMode).toBe('json')
    expect(JSON.parse(jsonDraft.bodyTemplateText)).toEqual({ text: '{{text}}' })
    expect(jsonDraft.headers.map((row) => [row.key, row.value])).toEqual([
      ['Content-Type', 'application/json'],
    ])
    expect(jsonDraft.vendorAdapter).toBe('OpenAIAdapter')

    const rawDraft = requestTemplateDraftFromMeta({ body_template: '{"text":"${text}"}' })
    expect(rawDraft.bodyTemplateMode).toBe('raw')
    expect(rawDraft.bodyTemplateText).toBe('{"text":"${text}"}')
  })

  it('缺省 meta → 空草稿（不抛错）', () => {
    const draft = requestTemplateDraftFromMeta(null)
    expect(draft.method).toBe('')
    expect(draft.headers).toEqual([])
    expect(draft.wsHeaders).toEqual([])
    expect(draft.vendorAdapter).toBe('')
  })

  it('WS 键回填（ws_headers / session_config / pacing）', () => {
    const draft = requestTemplateDraftFromMeta({
      ws_headers: { Authorization: 'Bearer x' },
      session_config: { turn_detection: true },
      pacing: { interval_ms: 200 },
    })
    expect(draft.wsHeaders.map((row) => row.key)).toEqual(['Authorization'])
    expect(JSON.parse(draft.sessionConfig)).toEqual({ turn_detection: true })
    expect(JSON.parse(draft.pacing)).toEqual({ interval_ms: 200 })
  })
})

describe('mergeRequestTemplateMeta（后端整块 replace → 前端合并）', () => {
  it('HTTP 组：只覆盖声明的键，未知键原样保留', () => {
    const base = { protocol: 'https', environment: 'development', appendix_test: 1, method: 'GET' }
    const draft = requestTemplateDraftFromMeta(base)
    draft.method = 'POST'
    draft.bodyTemplateText = '{"text":"{{text}}"}'
    draft.vendorAdapter = 'HttpAdapter'

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, 'http_api')
    expect(errors).toEqual([])
    expect(meta).toEqual({
      protocol: 'https',
      environment: 'development',
      appendix_test: 1,
      method: 'POST',
      body_template: { text: '{{text}}' },
      vendor_adapter: 'HttpAdapter',
    })
  })

  it('清空某键 → 从 base 删除该键（不写 null）', () => {
    const base = { method: 'POST', headers: { a: 'b' }, vendor_adapter: 'X' }
    const draft = requestTemplateDraftFromMeta(base)
    draft.method = ''
    draft.headers = []
    draft.vendorAdapter = '   '

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, 'http_api')
    expect(errors).toEqual([])
    expect(meta).toEqual({})
    expect('method' in meta).toBe(false)
    expect('headers' in meta).toBe(false)
    expect('vendor_adapter' in meta).toBe(false)
  })

  it('WS 组保存不删 HTTP 旧键（切换设备类型只隐藏）', () => {
    const base = { method: 'POST', headers: { a: 'b' }, appendix_test: 1 }
    const draft = requestTemplateDraftFromMeta(base)
    draft.wsHeaders = [newKeyValueRow('Authorization', 'Bearer x')]
    draft.sessionConfig = '{"turn_detection": true}'
    draft.pacing = '{"interval_ms": 200}'

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, 'websocket_api')
    expect(errors).toEqual([])
    expect(meta.method).toBe('POST')
    expect(meta.headers).toEqual({ a: 'b' })
    expect(meta.ws_headers).toEqual({ Authorization: 'Bearer x' })
    expect(meta.session_config).toEqual({ turn_detection: true })
    expect(meta.pacing).toEqual({ interval_ms: 200 })
    expect(meta.appendix_test).toBe(1)
  })

  it('非法 JSON → 返回字段级错误（调用方拦截保存）', () => {
    const draft = requestTemplateDraftFromMeta({})
    draft.bodyTemplateText = '{bad json'
    const { errors } = mergeRequestTemplateMeta({}, draft, 'http_api')
    expect(errors).toEqual([{ field: 'bodyTemplate', message: '请求体模板 JSON 格式不正确' }])

    const wsDraft = requestTemplateDraftFromMeta({})
    wsDraft.sessionConfig = '[1,2]'
    const wsResult = mergeRequestTemplateMeta({}, wsDraft, 'websocket_api')
    expect(wsResult.errors).toEqual([
      { field: 'sessionConfig', message: '会话配置必须是 JSON 对象' },
    ])
  })

  it('请求头键名为空 / 重复 → 拦截', () => {
    const draft = requestTemplateDraftFromMeta({})
    draft.headers = [newKeyValueRow('', 'v'), newKeyValueRow('a', '1'), newKeyValueRow('a', '2')]
    const { errors } = mergeRequestTemplateMeta({}, draft, 'http_api')
    expect(errors).toEqual([
      { field: 'headers', message: '请求头名称不能为空' },
      { field: 'headers', message: '请求头名称重复：a' },
    ])
  })
})

describe('deriveDraftTargetDeviceType（新增态按端点草稿派生）', () => {
  it('显式 deviceType 优先', () => {
    expect(deriveDraftTargetDeviceType('http_api', [{ endpoint: 'ws://x' }])).toBe('http_api')
  })

  it('auto 按首个非空端点协议派生；无端点缺省 http_api', () => {
    expect(deriveDraftTargetDeviceType('auto', [{ endpoint: 'wss://api.example.com' }])).toBe(
      'websocket_api'
    )
    expect(deriveDraftTargetDeviceType('auto', [{ endpoint: 'https://api.example.com' }])).toBe(
      'http_api'
    )
    expect(deriveDraftTargetDeviceType('auto', [])).toBe('http_api')
  })
})

describe('audio_config（顶层列四项）', () => {
  it('回填 bit_depth 数字别名 16/24/32 → s16/s24/s32', () => {
    expect(
      audioConfigDraftFrom({
        sample_rate: 16000,
        bit_depth: 16,
        channels: 1,
        container: 'pcm',
      })
    ).toEqual({ sampleRate: '16000', bitDepth: 's16', channels: '1', container: 'pcm' })
  })

  it('null → 全空草稿', () => {
    expect(audioConfigDraftFrom(null)).toEqual({
      sampleRate: '',
      bitDepth: '',
      channels: '',
      container: '',
    })
  })

  it('保存保留 base 中本页签不编辑的已知键（format / chunk_duration_ms）', () => {
    const base = { format: 'pcm', chunk_duration_ms: 100, sample_rate: 8000 }
    const draft = audioConfigDraftFrom(base)
    draft.sampleRate = '24000'
    draft.channels = '2'
    expect(buildAudioConfig(base, draft)).toEqual({
      format: 'pcm',
      chunk_duration_ms: 100,
      sample_rate: 24000,
      channels: 2,
    })
  })

  it('四项全清空 → 空对象（显式清除）', () => {
    const base = { sample_rate: 8000, bit_depth: 's16', channels: 1, container: 'pcm' }
    const draft = audioConfigDraftFrom(base)
    draft.sampleRate = ''
    draft.bitDepth = ''
    draft.channels = ''
    draft.container = ''
    expect(buildAudioConfig(base, draft)).toEqual({})
  })
})
