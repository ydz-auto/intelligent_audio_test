/**
 * 用例列表项适配器单测（接线卡 INT-922 P2-1）：
 * testCaseListItemFromDto 携带 config / algorithm_params / reference_params
 * 原样透传（编辑回填与保存合并的数据源），轮次数/音频数由 config.rounds 派生。
 */
import { describe, expect, it } from 'vitest'

import type { CaseResultForReview } from '@/domain/models/review'
import {
  caseDetailFromDto,
  testCaseListItemFromDto,
  testCasePreviewFromDto,
} from '@/infrastructure/adapters/testCaseAdapter'
import type { CaseDetailDto, TestCaseListItemDto } from '@/infrastructure/dto/testcase.dto'

const DTO: TestCaseListItemDto = {
  id: 'tc-1',
  name: '客厅_中文_命令集',
  description: '描述',
  group_id: 'g-1',
  group_name: '客厅',
  type: 'api',
  tags: ['客厅', '中文'],
  algorithm_type: 'voice_llm',
  total_duration: 120,
  config: {
    rounds: [
      {
        round_number: 1,
        audios: [
          { audio_id: 101, audio_name: '客厅_中文_命令集.wav', spl: 65 },
          { audio_id: 102, audio_name: '车内_导航_1人.wav', spl: 70 },
        ],
        evaluation: {
          enabled: true,
          dimensions: [
            { id: 5, name: 'LLM语义评分', weight: 50, threshold: 80 },
            { id: 11, name: '语音活动检测', weight: 50, threshold: 80 },
          ],
        },
      },
      {
        round_number: 2,
        audios: [{ audio_id: 103, audio_name: '会议室_多人_中文.wav', spl: 65 }],
        evaluation: { enabled: false, dimensions: [] },
      },
    ],
    dimensions: [],
  },
  algorithm_params: [
    { round_number: 1, params: [{ field_code: 'voiceprint', field_value: { audio_id: 101 } }] },
  ],
  reference_params: [{ round_number: 1, reference_params_path: 'refs/客厅/1.txt' }],
}

describe('testCaseListItemFromDto（INT-922）', () => {
  it('config / algorithmParams / referenceParams 原样透传，轮次/音频数派生', () => {
    const item = testCaseListItemFromDto(DTO)
    expect(item).toMatchObject({
      id: 'tc-1',
      groupId: 'g-1',
      algorithmType: 'voice_llm',
      rounds: 2,
      audioCount: 3,
    })
    // config 值内 snake_case 契约原样保留（编辑回填数据源）
    const configRounds = (item.config?.rounds ?? []) as Array<Record<string, unknown>>
    expect(configRounds).toHaveLength(2)
    expect(configRounds[0]).toMatchObject({
      round_number: 1,
      evaluation: { enabled: true, dimensions: [{ id: 5 }, { id: 11 }] },
    })
    expect(configRounds[0].audios as Array<{ audio_id: number }>).toHaveLength(2)
    expect(item.algorithmParams).toEqual(DTO.algorithm_params)
    expect(item.referenceParams).toEqual(DTO.reference_params)
  })

  it('config 缺省时透传 null，轮次默认 1', () => {
    const item = testCaseListItemFromDto({
      ...DTO,
      config: { rounds: null, dimensions: [] },
    })
    expect(item.config).toEqual({ rounds: null, dimensions: [] })
    expect(item.rounds).toBe(1)
    expect(item.audioCount).toBe(0)
  })
})

/**
 * infrastructure/adapters/testCaseAdapter 纯函数测试（10 规范 §5.2 / §9，INT-1066）。
 * 对位 task_bp.py get_case_detail 实测响应：case_name（无 name 字段）+ algorithm_results 扁平项
 * + devices。返工 P1：case_name → name 映射；P2：algorithm_results → 领域模型消费。
 */
describe('caseDetailFromDto', () => {
  it('后端返回 case_name（无 name 字段）→ 领域 name 正确映射（P1）', () => {
    const detail = caseDetailFromDto({
      test_case_id: '5412e6d4-be58-4446-9dc0-d40f739e919f',
      task_id: 1257,
      case_name: 'API用例',
      execution_status: 'failed',
      evaluation_status: 'completed',
      duration: null,
      score: null,
      algorithm_type: 'voice_llm',
      algorithm_results: [],
      devices: [],
    })
    expect(detail.name).toBe('API用例')
    expect(detail.caseId).toBe('5412e6d4-be58-4446-9dc0-d40f739e919f')
    expect(detail.taskId).toBe(1257)
    // P3：duration null 保持 null（头部不渲染「耗时」，旧 Vue 同口径），不做 ?? 0 兜底
    expect(detail.duration).toBeNull()
    expect(detail.algorithmType).toBe('voice_llm')
  })

  it('case_name 缺省时回退 name 字段（兼容留底）', () => {
    const detail = caseDetailFromDto({
      test_case_id: 'case-x',
      task_id: 1,
      name: '旧字段用例',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: 5,
      score: 90,
      algorithm_type: null,
      algorithm_results: [],
      devices: [],
    } as never)
    expect(detail.name).toBe('旧字段用例')
  })

  it('algorithm_results snake_case 扁平项 → camelCase 领域数组（P2）', () => {
    const detail = caseDetailFromDto({
      test_case_id: 'case-y',
      task_id: 2,
      case_name: 'API用例二',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: 10,
      score: null,
      algorithm_type: 'voice_llm',
      algorithm_results: [
        {
          param_code: 'round_count',
          param_type: 'number',
          label: 'round count',
          value: 2,
        },
        {
          param_code: 'rounds',
          param_type: 'json',
          label: 'round results',
          value: [{ round_number: 1, success: true }],
        },
      ],
      devices: [],
    })
    expect(detail.algorithmResults).toEqual([
      { paramCode: 'round_count', paramType: 'number', label: 'round count', value: 2 },
      { paramCode: 'rounds', paramType: 'json', label: 'round results', value: [{ round_number: 1, success: true }] },
    ])
  })

  it('devices 为设备名字符串数组（真实后端形态）→ 设备行按名称映射', () => {
    const detail = caseDetailFromDto({
      test_case_id: 'case-z',
      task_id: 3,
      case_name: 'E2E用例',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: 8,
      score: 85,
      algorithm_type: null,
      algorithm_results: [],
      devices: ['pura90豆包'],
    })
    expect(detail.devices).toHaveLength(1)
    expect(detail.devices[0]).toMatchObject({
      deviceName: 'pura90豆包',
      executionStatus: null,
      metrics: [],
    })
    expect(detail.metricColumns).toEqual([])
    expect(detail.multiRound).toBe(false)
  })

  /**
   * INT-1688：真实库栈任务 402 / 用例 7bac162b-… 实测原文夹具——
   * detail.devices=["pura90小艺"]（字符串数组）、metric_configs 6 项、
   * algorithm_results 含 user_wav@round:1 / ai_wav@round:1（param_type=audio_file）；
   * 维度值在 /results 结果行的 dimensions（round_number null=整体、0=第1轮）。
   */
  describe('INT-1688 真实响应形态（任务 402 用例实测夹具）', () => {
    const detailDto: CaseDetailDto = {
      test_case_id: '7bac162b-275d-4567-b924-954736dc3ce9',
      task_id: 402,
      case_name: '测试用例_JG0006_单轮接管',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: null,
      score: null,
      algorithm_type: 'voice_llm',
      devices: ['pura90小艺'],
      metric_configs: [
        { code: '逐轮话轮评估', name: '逐轮话轮评估' },
        { code: '接管率占比', name: '接管率占比' },
        { code: '未接管率占比', name: '未接管率占比' },
        { code: '误接管率占比', name: '误接管率占比' },
        { code: '接管时延平均值', name: '接管时延平均值' },
        { code: '接管内容平均分', name: '接管内容平均分' },
      ],
      algorithm_results: [
        {
          param_code: 'user_wav@round:1',
          param_type: 'audio_file',
          label: 'user_wav (第1轮)',
          round_number: 1,
          device: '9-pura90小艺-1.0.0',
          value: 'case_pcm/402/xxx/r0_in.wav',
        },
        {
          param_code: 'ai_wav@round:1',
          param_type: 'audio_file',
          label: 'ai_wav (第1轮)',
          round_number: 1,
          device: '9-pura90小艺-1.0.0',
          value: 'case_pcm/402/xxx/r0_out.wav',
        },
        { param_code: 'tc_turns@round:1', param_type: 'json', label: '逐轮接管判定', value: [] },
      ],
      result_audios: {},
      audio_list: [
        { id: 1622, filename: 'JG0006_输入.wav', duration: 3.167, url: '/api/v1/audios/1622/stream' },
      ],
    }
    const results: CaseResultForReview[] = [
      {
        id: 3967,
        deviceId: 9,
        deviceName: 'pura90小艺',
        apiId: null,
        apiName: null,
        executionStatus: 'completed',
        responseTime: 0,
        errorMessage: null,
        reviewed: false,
        reviewedByUserId: null,
        reviewedAt: null,
        lastReviewComment: null,
        lastReviewAction: null,
        reviewHistory: [],
        sourceTaskId: 402,
        sourceTaskName: null,
        asrResult: null,
        translationResult: null,
        dimensions: [
          { dimensionId: 84, name: '接管率占比', value: 1.0, score: 1.0, status: 'completed', evaluationStatus: 'completed', errorMessage: null, roundNumber: null },
          { dimensionId: 84, name: '接管率占比', value: 1.0, score: 1.0, status: 'completed', evaluationStatus: 'completed', errorMessage: null, roundNumber: 0 },
          { dimensionId: 72, name: '逐轮话轮评估', value: null, score: 0.0, status: 'completed', evaluationStatus: 'completed', errorMessage: null, roundNumber: null },
          { dimensionId: 72, name: '逐轮话轮评估', value: null, score: 0.0, status: 'completed', evaluationStatus: 'completed', errorMessage: null, roundNumber: 0 },
        ],
      },
    ]

    it('设备名出真实值、执行状态取结果行（不再恒「失败」）', () => {
      const detail = caseDetailFromDto(detailDto, results)
      expect(detail.devices).toHaveLength(1)
      expect(detail.devices[0].deviceName).toBe('pura90小艺')
      expect(detail.devices[0].executionStatus).toBe('completed')
      expect(detail.devices[0].resultId).toBe(3967)
    })

    it('维度列按 metric_configs 顺序展开（@round:{rn+1} 在前、@overall 在后）', () => {
      const detail = caseDetailFromDto(detailDto, results)
      expect(detail.multiRound).toBe(true)
      expect(detail.metricColumns.map((c) => c.key)).toEqual([
        '逐轮话轮评估@round:1',
        '逐轮话轮评估@overall',
        '接管率占比@round:1',
        '接管率占比@overall',
      ])
      expect(detail.devices[0].metrics).toEqual(
        expect.arrayContaining([
          { dimension: '接管率占比', round: 1, value: '1' },
          { dimension: '接管率占比', round: undefined, value: '1' },
          { dimension: '逐轮话轮评估', round: 1, value: '—' },
        ])
      )
    })

    it('结果音频：algorithm_results 的 audio_file 项转可试听音频（path 供 stream-by-path）', () => {
      const detail = caseDetailFromDto(detailDto, results)
      expect(detail.resultAudios).toEqual([
        {
          audioName: 'user_wav (第1轮)',
          deviceName: null,
          url: null,
          path: 'case_pcm/402/xxx/r0_in.wav',
        },
        {
          audioName: 'ai_wav (第1轮)',
          deviceName: null,
          url: null,
          path: 'case_pcm/402/xxx/r0_out.wav',
        },
      ])
      expect(detail.referenceAudios).toEqual([
        {
          audioName: 'JG0006_输入.wav',
          deviceName: null,
          audioId: 1622,
          url: '/api/v1/audios/1622/stream',
          path: null,
        },
      ])
    })

    it('无结果行（未完成/秒败）→ 设备名保留、无维度列、无结果音频', () => {
      const detail = caseDetailFromDto(
        { ...detailDto, algorithm_results: [], audio_list: [] },
        []
      )
      expect(detail.devices.map((d) => d.deviceName)).toEqual(['pura90小艺'])
      expect(detail.devices[0].executionStatus).toBeNull()
      expect(detail.metricColumns).toEqual([])
      expect(detail.resultAudios).toEqual([])
      expect(detail.results).toEqual([])
    })
  })
})

describe('testCasePreviewFromDto（INT-1534 试听接线）', () => {
  it('frontend 多轮：audio_stream_urls 优先，单键回退，playback_mode 归一为二值', () => {
    const preview = testCasePreviewFromDto({
      test_case_id: 'tc-1',
      status: 'frontend_preview_ready',
      message: '前端播放模式，返回音频流URL',
      duration: 12.5,
      playback_mode: 'frontend',
      audio_id: 101,
      audio_stream_url: '/api/v1/audios/download?path=a.wav',
      audio_stream_urls: [
        '/api/v1/audios/download?path=a.wav',
        '/api/v1/audios/download?path=b.wav',
      ],
    })
    expect(preview).toMatchObject({
      testCaseId: 'tc-1',
      playbackMode: 'frontend',
      duration: 12.5,
      audioId: 101,
      audioStreamUrl: '/api/v1/audios/download?path=a.wav',
    })
    expect(preview.audioStreamUrls).toHaveLength(2)
  })

  it('backend 无流地址：audio_stream_urls 空数组，时长可为 null，playback_mode 兜底 backend', () => {
    const preview = testCasePreviewFromDto({
      test_case_id: 'tc-2',
      status: 'preview_started',
      duration: null,
      audio_stream_url: null,
    })
    expect(preview.playbackMode).toBe('backend')
    expect(preview.duration).toBeNull()
    expect(preview.audioStreamUrls).toEqual([])
  })
})
