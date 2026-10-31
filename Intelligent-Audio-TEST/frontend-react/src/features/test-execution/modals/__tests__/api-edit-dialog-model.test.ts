/**
 * INT-1777 / INT-1778：API 编辑弹窗请求模板 / 响应解析 / audio_config 草稿模型单测。
 * 锁定母卡 §3.1 的 meta 合并规则（base 保留未知键、清空删键、隐藏组不删）、
 * §2.3 响应解析 8 键口径与 audio_config 顶层列四项口径。
 */
import { describe, expect, it } from 'vitest'

import {
  audioConfigDraftFrom,
  buildAudioConfig,
  emptyResponseParserDraft,
  mergeRequestTemplateMeta,
  mergeResponseParserMeta,
  newKeyValueRow,
  requestTemplateDraftFromMeta,
  responseParserDraftFromMeta,
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
    const base = { version: 'v1', environment: 'development', appendix_test: 1, method: 'GET' }
    const draft = requestTemplateDraftFromMeta(base)
    draft.method = 'POST'
    draft.bodyTemplateText = '{"text":"{{text}}"}'
    draft.vendorAdapter = 'HttpAdapter'

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, { protocol: 'http', streaming: false })
    expect(errors).toEqual([])
    expect(meta).toEqual({
      version: 'v1',
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

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, { protocol: 'http', streaming: false })
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

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, { protocol: 'websocket', streaming: true })
    expect(errors).toEqual([])
    expect(meta.method).toBe('POST')
    expect(meta.headers).toEqual({ a: 'b' })
    expect(meta.ws_headers).toEqual({ Authorization: 'Bearer x' })
    expect(meta.session_config).toEqual({ turn_detection: true })
    expect(meta.pacing).toEqual({ interval_ms: 200 })
    expect(meta.appendix_test).toBe(1)
  })

  it('WS 两段载荷：首帧 / 音频帧按开关写 meta，关闭即删键', () => {
    const draft = requestTemplateDraftFromMeta({
      first_frame: { enabled: true, template: { type: 'session.update', session: {} } },
      audio_frame: { enabled: true, template: { type: 'input_audio_buffer.append', audio: '{{audio_b64}}' } },
    })
    expect(draft.firstFrameEnabled).toBe(true)
    expect(draft.audioFrameEnabled).toBe(true)

    const kept = mergeRequestTemplateMeta(
      {},
      { ...draft, firstFrameTemplate: '{"type":"session.update"}', audioFrameTemplate: '{"audio":"{{audio_b64}}"}' },
      { protocol: 'websocket', streaming: true }
    )
    expect(kept.errors).toEqual([])
    expect(kept.meta.first_frame).toEqual({ enabled: true, template: { type: 'session.update' } })
    expect(kept.meta.audio_frame).toEqual({ enabled: true, template: { audio: '{{audio_b64}}' } })

    // 关闭开关 → 两个键都删掉，回落执行侧默认载荷
    const cleared = mergeRequestTemplateMeta(kept.meta, {
      ...draft,
      firstFrameEnabled: false,
      audioFrameEnabled: false,
    }, { protocol: 'websocket', streaming: true })
    expect('first_frame' in cleared.meta).toBe(false)
    expect('audio_frame' in cleared.meta).toBe(false)
  })

  it('WS 载荷开关打开但模板为空 → 字段级错误', () => {
    const draft = requestTemplateDraftFromMeta({})
    const { errors } = mergeRequestTemplateMeta({}, {
      ...draft,
      firstFrameEnabled: true,
      firstFrameTemplate: '   ',
    }, { protocol: 'websocket', streaming: true })
    expect(errors).toEqual([
      { field: 'firstFrameTemplate', message: '首帧载荷不能为空（关闭开关即回落默认载荷）' },
    ])
  })

  it('非法 JSON → 返回字段级错误（调用方拦截保存）', () => {
    const draft = requestTemplateDraftFromMeta({})
    draft.bodyTemplateText = '{bad json'
    const { errors } = mergeRequestTemplateMeta({}, draft, { protocol: 'http', streaming: false })
    expect(errors).toEqual([{ field: 'bodyTemplate', message: '请求体模板 JSON 格式不正确' }])

    const wsDraft = requestTemplateDraftFromMeta({})
    wsDraft.sessionConfig = '[1,2]'
    const wsResult = mergeRequestTemplateMeta({}, wsDraft, { protocol: 'websocket', streaming: true })
    expect(wsResult.errors).toEqual([
      { field: 'sessionConfig', message: '会话配置必须是 JSON 对象' },
    ])
  })

  it('请求头键名为空 / 重复 → 拦截', () => {
    const draft = requestTemplateDraftFromMeta({})
    draft.headers = [newKeyValueRow('', 'v'), newKeyValueRow('a', '1'), newKeyValueRow('a', '2')]
    const { errors } = mergeRequestTemplateMeta({}, draft, { protocol: 'http', streaming: false })
    expect(errors).toEqual([
      { field: 'headers', message: '请求头名称不能为空' },
      { field: 'headers', message: '请求头名称重复：a' },
    ])
  })
})

describe('响应解析页签（INT-1778 §2.3；负责人 2026-10-31 起只写 result_parser / append_mode）', () => {
  it('编辑态回填 result_parser 与 append_mode；6 个 *_mapping 不再进草稿', () => {
    const draft = responseParserDraftFromMeta({
      result_parser: { asr_text_path: 'data.text', session_id_path: 'data.sid' },
      asr_mapping: 'data.asr.text',
      trans_mapping: 'data.translation',
      sentence_end_mapping: 'data.is_end',
      session_end_mapping: 'data.finished',
      error_code_mapping: 'code',
      error_msg_mapping: 'msg',
      append_mode: true,
    })
    expect(JSON.parse(draft.resultParser)).toEqual({
      asr_text_path: 'data.text',
      session_id_path: 'data.sid',
    })
    expect(draft.appendMode).toBe('true')
    expect(draft).not.toHaveProperty('asrMapping')
    expect(draft).not.toHaveProperty('transMapping')

    expect(responseParserDraftFromMeta({ append_mode: false }).appendMode).toBe('false')
    expect(responseParserDraftFromMeta({}).appendMode).toBe('')
    expect(responseParserDraftFromMeta(null)).toEqual(emptyResponseParserDraft())
  })

  it('保存：只覆盖声明键，请求模板 / 未知键 / 存量 *_mapping 原样保留', () => {
    const base = {
      protocol: 'wss',
      appendix_test: 1,
      method: 'POST',
      body_template: { text: '{{text}}' },
      asr_mapping: 'old.path',
      error_code_mapping: 'code',
    }
    const draft = responseParserDraftFromMeta(base)
    draft.resultParser = '{"asr_text_path":"data.text"}'

    const { meta, errors } = mergeResponseParserMeta(base, draft)
    expect(errors).toEqual([])
    expect(meta).toEqual({
      protocol: 'wss',
      appendix_test: 1,
      method: 'POST',
      body_template: { text: '{{text}}' },
      asr_mapping: 'old.path',
      error_code_mapping: 'code',
      result_parser: { asr_text_path: 'data.text' },
    })
  })

  it('清空声明键 → 从 base 删除（后端回落到内置缺省），存量 *_mapping 不动', () => {
    const base = {
      result_parser: { asr_text_path: 'a' },
      append_mode: true,
      asr_mapping: 'a',
      appendix_test: 1,
    }
    const draft = responseParserDraftFromMeta(base)
    draft.resultParser = ''
    draft.appendMode = ''

    const { meta, errors } = mergeResponseParserMeta(base, draft)
    expect(errors).toEqual([])
    expect(meta).toEqual({ asr_mapping: 'a', appendix_test: 1 })
  })

  it('append_mode 三态：true / false 写布尔，末态为空串则删键', () => {
    const truthy = mergeResponseParserMeta({}, { ...emptyResponseParserDraft(), appendMode: 'true' })
    expect(truthy.meta.append_mode).toBe(true)
    const falsy = mergeResponseParserMeta({}, { ...emptyResponseParserDraft(), appendMode: 'false' })
    expect(falsy.meta.append_mode).toBe(false)
  })

  it('result_parser 非法 JSON / 非对象 → 字段级错误（调用方拦截保存）', () => {
    const broken = mergeResponseParserMeta(
      {},
      { ...emptyResponseParserDraft(), resultParser: '{bad json' }
    )
    expect(broken.errors).toEqual([
      { field: 'resultParser', message: '响应解析器 JSON 格式不正确' },
    ])

    const arrayValue = mergeResponseParserMeta(
      {},
      { ...emptyResponseParserDraft(), resultParser: '[1,2]' }
    )
    expect(arrayValue.errors).toEqual([
      { field: 'resultParser', message: '响应解析器必须是 JSON 对象' },
    ])
  })

  it('两个写 meta 的页签串行合并：互不覆盖对方声明的键', () => {
    const base = { appendix_test: 1 }
    const requestDraft = requestTemplateDraftFromMeta(base)
    requestDraft.method = 'POST'
    const requestMeta = mergeRequestTemplateMeta(base, requestDraft, { protocol: 'http', streaming: false }).meta

    const responseMeta = mergeResponseParserMeta(requestMeta, {
      ...emptyResponseParserDraft(),
      appendMode: 'true',
    }).meta
    expect(responseMeta).toEqual({
      appendix_test: 1,
      method: 'POST',
      append_mode: true,
    })
  })
})

describe('A3 / INT-1791：gRPC 组（meta.grpc 子对象级合并 + 字段级校验）', () => {
  it('回填 meta.grpc 八键', () => {
    const draft = requestTemplateDraftFromMeta({
      grpc: {
        proto_object_key: 'api-protos/abc.proto',
        proto_sha256: 'a'.repeat(64),
        proto_size: 1024,
        service: 'demo.Echo',
        method: 'Say',
        method_kind: 'unary',
        metadata: { 'x-api-key': 'k' },
        deadline_ms: 5000,
      },
    })
    expect(draft.grpcProtoObjectKey).toBe('api-protos/abc.proto')
    expect(draft.grpcProtoSha256).toBe('a'.repeat(64))
    expect(draft.grpcProtoSize).toBe('1024')
    expect(draft.grpcService).toBe('demo.Echo')
    expect(draft.grpcMethod).toBe('Say')
    expect(draft.grpcMethodKind).toBe('unary')
    expect(draft.grpcMetadata.map((row) => [row.key, row.value])).toEqual([['x-api-key', 'k']])
    expect(draft.grpcDeadlineMs).toBe('5000')
  })

  it('保存：以 base 的 meta.grpc 为底逐子键覆盖，未声明子键原样保留（不整块重建）', () => {
    const base = {
      method: 'POST',
      grpc: { proto_object_key: 'old.proto', future_key: 'keep-me', service: 'old.Svc' },
      appendix_test: 1,
    }
    const draft = requestTemplateDraftFromMeta(base)
    draft.grpcProtoObjectKey = 'new.proto'
    draft.grpcService = 'demo.Echo'
    draft.grpcMethod = 'Say'
    draft.grpcMethodKind = 'unary'
    draft.grpcMetadata = [newKeyValueRow('authorization', 'Bearer x')]
    draft.grpcDeadlineMs = '3000'

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, {
      protocol: 'grpc',
      streaming: false,
    })
    expect(errors).toEqual([])
    expect(meta.grpc).toEqual({
      // 未声明子键保留、旧值被覆盖
      future_key: 'keep-me',
      proto_object_key: 'new.proto',
      service: 'demo.Echo',
      method: 'Say',
      method_kind: 'unary',
      metadata: { authorization: 'Bearer x' },
      deadline_ms: 3000,
    })
    // gRPC 组不写 HTTP / WS 组键，也不动别的页签
    expect(meta.method).toBe('POST')
    expect(meta.appendix_test).toBe(1)
    expect('body_template' in meta).toBe(false)
  })

  it('切到别的协议保存：meta.grpc 整块原样保留（隐藏组不删）', () => {
    const base = { grpc: { service: 'demo.Echo', method: 'Say', method_kind: 'unary' } }
    const httpDraft = requestTemplateDraftFromMeta(base)
    httpDraft.method = 'GET'
    const { meta } = mergeRequestTemplateMeta(base, httpDraft, {
      protocol: 'http',
      streaming: false,
    })
    expect(meta.grpc).toEqual({ service: 'demo.Echo', method: 'Say', method_kind: 'unary' })
  })

  it('必填缺失 / method_kind 非法 / deadline ≤ 0 / metadata 大写键与换行 → 字段级错误', () => {
    const missing = mergeRequestTemplateMeta({}, requestTemplateDraftFromMeta({}), {
      protocol: 'grpc',
      streaming: false,
    })
    expect(missing.errors.map((error) => error.field)).toEqual([
      'grpcProto',
      'grpcService',
      'grpcMethod',
      'grpcMethodKind',
    ])

    const draft = requestTemplateDraftFromMeta({})
    draft.grpcProtoObjectKey = 'api-protos/a.proto'
    draft.grpcService = 'demo.Echo'
    draft.grpcMethod = 'Say'
    draft.grpcMethodKind = 'streaming'
    draft.grpcDeadlineMs = '0'
    draft.grpcMetadata = [
      newKeyValueRow('X-Api-Key', 'k'),
      newKeyValueRow('authorization', 'a\r\nb'),
    ]
    const { errors } = mergeRequestTemplateMeta({}, draft, {
      protocol: 'grpc',
      streaming: false,
    })
    expect(errors).toEqual([
      { field: 'grpcMethodKind', message: 'method_kind 非法：streaming（合法值：unary / server_stream / bidi）' },
      { field: 'grpcDeadlineMs', message: 'deadline_ms（毫秒）必须为正数' },
      { field: 'grpcMetadata', message: 'metadata 名称必须为小写：X-Api-Key' },
      { field: 'grpcMetadata', message: 'metadata 值不能包含换行：authorization' },
    ])
  })

  it('proto_sha256 / proto_size 越界 → 拦截', () => {
    const draft = requestTemplateDraftFromMeta({})
    draft.grpcProtoObjectKey = 'api-protos/a.proto'
    draft.grpcProtoSha256 = 'XYZ'
    draft.grpcProtoSize = '999999'
    draft.grpcService = 'demo.Echo'
    draft.grpcMethod = 'Say'
    draft.grpcMethodKind = 'bidi'
    const { errors } = mergeRequestTemplateMeta({}, draft, {
      protocol: 'grpc',
      streaming: true,
    })
    expect(errors).toEqual([
      { field: 'grpcProto', message: 'proto_sha256 必须为 64 位小写十六进制' },
      { field: 'grpcProto', message: 'proto 文件超过 262144 字节上限' },
    ])
  })

  it('子键全部清空 → 删掉 meta.grpc 整个键（不写空对象）', () => {
    const base = { grpc: { service: 'demo.Echo', method: 'Say', method_kind: 'unary' } }
    const draft = requestTemplateDraftFromMeta(base)
    draft.grpcService = ''
    draft.grpcMethod = ''
    draft.grpcMethodKind = ''
    const { meta } = mergeRequestTemplateMeta(base, draft, {
      protocol: 'grpc',
      streaming: false,
    })
    expect('grpc' in meta).toBe(false)
  })
})

describe('A3 / INT-1791：SSE 组（meta.sse 子对象 + method / headers 复用，不写 body_template）', () => {
  it('回填 meta.sse 七键 + 共用 method / headers', () => {
    const draft = requestTemplateDraftFromMeta({
      method: 'POST',
      headers: { Accept: 'text/event-stream' },
      sse: {
        event_name_field: 'evt',
        params: { token: '{{token}}' },
        reconnect_enabled: true,
        max_reconnect_attempts: 3,
        retry_ms: 2000,
        idle_timeout_ms: 60000,
        max_duration_ms: 300000,
      },
    })
    expect(draft.method).toBe('POST')
    expect(draft.headers.map((row) => row.key)).toEqual(['Accept'])
    expect(draft.sseEventNameField).toBe('evt')
    expect(draft.sseParams.map((row) => [row.key, row.value])).toEqual([['token', '{{token}}']])
    expect(draft.sseReconnectEnabled).toBe(true)
    expect(draft.sseMaxReconnectAttempts).toBe('3')
    expect(draft.sseRetryMs).toBe('2000')
    expect(draft.sseIdleTimeoutMs).toBe('60000')
    expect(draft.sseMaxDurationMs).toBe('300000')
  })

  it('保存：写 method / headers + meta.sse，且不写 body_template；别的键原样保留', () => {
    const base = {
      body_template: { text: '{{text}}' },
      sse: { unknownKept: true, retry_ms: 1000 },
      appendix_test: 1,
    }
    const draft = requestTemplateDraftFromMeta(base)
    draft.method = 'GET'
    draft.headers = [newKeyValueRow('Accept', 'text/event-stream')]
    draft.sseEventNameField = 'event'
    draft.sseParams = [newKeyValueRow('token', 'abc')]
    draft.sseReconnectEnabled = true
    draft.sseMaxReconnectAttempts = '5'
    draft.sseRetryMs = '0'
    draft.sseIdleTimeoutMs = '30000'
    draft.sseMaxDurationMs = ''

    const { meta, errors } = mergeRequestTemplateMeta(base, draft, {
      protocol: 'sse',
      streaming: true,
    })
    expect(errors).toEqual([])
    expect(meta.method).toBe('GET')
    expect(meta.headers).toEqual({ Accept: 'text/event-stream' })
    expect(meta.body_template).toEqual({ text: '{{text}}' })
    expect(meta.sse).toEqual({
      unknownKept: true,
      event_name_field: 'event',
      params: { token: 'abc' },
      reconnect_enabled: true,
      max_reconnect_attempts: 5,
      retry_ms: 0,
      idle_timeout_ms: 30000,
    })
    expect(meta.appendix_test).toBe(1)
    // SSE 是流式，但会话配置 / 节奏控制不归 SSE 组
    expect('session_config' in meta).toBe(false)
    expect('pacing' in meta).toBe(false)
  })

  it('越界 / 事件名全空白 → 字段级错误', () => {
    const draft = requestTemplateDraftFromMeta({})
    draft.sseEventNameField = '   '
    draft.sseRetryMs = '60001'
    draft.sseIdleTimeoutMs = '0'
    draft.sseMaxDurationMs = 'abc'
    draft.sseMaxReconnectAttempts = '11'
    const { errors } = mergeRequestTemplateMeta({}, draft, {
      protocol: 'sse',
      streaming: true,
    })
    expect(errors).toEqual([
      { field: 'sseEventNameField', message: '事件名字段必须为非空字符串（留空 = 使用缺省 event）' },
      { field: 'sseRetryMs', message: '重连退避上限（retry_ms）必须在 0-60000 之间' },
      { field: 'sseIdleTimeoutMs', message: '空闲超时（idle_timeout_ms）必须在 1-3600000 之间' },
      { field: 'sseMaxDurationMs', message: '整体时长上限（max_duration_ms）必须为整数' },
      { field: 'sseMaxReconnectAttempts', message: '重连次数上限（max_reconnect_attempts）必须在 0-10 之间' },
    ])
  })

  it('三页签都改过：请求模板（gRPC）+ 响应解析串行合并，互不覆盖', () => {
    const base = { appendix_test: 1 }
    const requestDraft = requestTemplateDraftFromMeta(base)
    requestDraft.grpcProtoObjectKey = 'api-protos/a.proto'
    requestDraft.grpcService = 'demo.Echo'
    requestDraft.grpcMethod = 'Say'
    requestDraft.grpcMethodKind = 'server_stream'
    requestDraft.vendorAdapter = 'GrpcAdapter'
    const requestMeta = mergeRequestTemplateMeta(base, requestDraft, {
      protocol: 'grpc',
      streaming: true,
    }).meta

    const responseMeta = mergeResponseParserMeta(requestMeta, {
      ...emptyResponseParserDraft(),
      appendMode: 'true',
    }).meta

    expect(responseMeta.grpc).toEqual({
      proto_object_key: 'api-protos/a.proto',
      service: 'demo.Echo',
      method: 'Say',
      method_kind: 'server_stream',
    })
    expect(responseMeta.vendor_adapter).toBe('GrpcAdapter')
    expect(responseMeta.append_mode).toBe(true)
    expect(responseMeta.appendix_test).toBe(1)
  })
})

describe('audio_config（输入 / 输出两套格式）', () => {
  it('存量扁平配置 → 输入输出两侧同值，bit_depth 数字别名归一', () => {
    expect(
      audioConfigDraftFrom({
        sample_rate: 16000,
        bit_depth: 16,
        channels: 1,
        container: 'pcm',
      })
    ).toEqual({
      input: { sampleRate: '16000', bitDepth: 's16', channels: '1', container: 'pcm' },
      output: { sampleRate: '16000', bitDepth: 's16', channels: '1', container: 'pcm' },
    })
  })

  it('分向对象优先于扁平；只配单侧时另一侧取同值', () => {
    const draft = audioConfigDraftFrom({
      sample_rate: 8000,
      input: { sample_rate: 16000, bit_depth: 's24', channels: 2, container: 'wav' },
    })
    expect(draft.input).toEqual({
      sampleRate: '16000',
      bitDepth: 's24',
      channels: '2',
      container: 'wav',
    })
    expect(draft.output.sampleRate).toBe('16000')
  })

  it('null → 两侧全空草稿', () => {
    expect(audioConfigDraftFrom(null)).toEqual({
      input: { sampleRate: '', bitDepth: '', channels: '', container: '' },
      output: { sampleRate: '', bitDepth: '', channels: '', container: '' },
    })
  })

  it('保存保留 base 中不编辑的已知键（format / chunk_duration_ms）并复制进两侧', () => {
    const base = { format: 'pcm', chunk_duration_ms: 100, sample_rate: 8000 }
    const draft = audioConfigDraftFrom(base)
    draft.input.sampleRate = '24000'
    draft.input.channels = '2'
    expect(buildAudioConfig(base, draft)).toEqual({
      format: 'pcm',
      chunk_duration_ms: 100,
      input: {
        format: 'pcm',
        chunk_duration_ms: 100,
        sample_rate: 24000,
        channels: 2,
      },
      output: {
        format: 'pcm',
        chunk_duration_ms: 100,
        sample_rate: 8000,
      },
    })
  })

  it('扁平四项改写为分向对象（不再写顶层四项）', () => {
    const base = { sample_rate: 8000, bit_depth: 's16', channels: 1, container: 'pcm' }
    const draft = audioConfigDraftFrom(base)
    draft.output.sampleRate = '16000'
    expect(buildAudioConfig(base, draft)).toEqual({
      input: { sample_rate: 8000, bit_depth: 's16', channels: 1, container: 'pcm' },
      output: { sample_rate: 16000, bit_depth: 's16', channels: 1, container: 'pcm' },
    })
  })

  it('两侧四项全清空 → 空对象（显式清除）', () => {
    const base = { sample_rate: 8000, bit_depth: 's16', channels: 1, container: 'pcm' }
    const draft = audioConfigDraftFrom(base)
    draft.input = { sampleRate: '', bitDepth: '', channels: '', container: '' }
    draft.output = { sampleRate: '', bitDepth: '', channels: '', container: '' }
    expect(buildAudioConfig(base, draft)).toEqual({})
  })
})
