/**
 * 用例列表项适配器单测（接线卡 INT-922 P2-1）：
 * testCaseListItemFromDto 携带 config / algorithm_params / reference_params
 * 原样透传（编辑回填与保存合并的数据源），轮次数/音频数由 config.rounds 派生。
 */
import { describe, expect, it } from 'vitest'

import type { CaseResultDimension, CaseResultForReview } from '@/domain/models/review'
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
    expect(detail.roundTabs).toEqual([
      { key: 'all', label: '指标', round: null, kind: 'all', rows: [] },
    ])
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

    it('轮次 Tab：第1轮 + 整体（整体有评估值才出），不是 @round 后缀宽表', () => {
      const detail = caseDetailFromDto(detailDto, results)
      expect(detail.roundTabs.map((t) => [t.key, t.label, t.kind])).toEqual([
        ['round:1', '第1轮', 'round'],
        ['overall', '整体', 'overall'],
      ])
      // 行=指标（metric_configs 顺序）、列=设备：单轮用例每个 Tab 只有 6 维度里的有值维度行
      expect(detail.roundTabs[0].rows).toEqual([
        { dimension: '逐轮话轮评估', values: { pura90小艺: '—' } },
        { dimension: '接管率占比', values: { pura90小艺: '1' } },
      ])
      expect(detail.roundTabs[1].rows).toEqual([
        { dimension: '逐轮话轮评估', values: { pura90小艺: '—' } },
        { dimension: '接管率占比', values: { pura90小艺: '1' } },
      ])
      expect(detail.devices[0].metrics).toEqual(
        expect.arrayContaining([
          { dimension: '接管率占比', round: 1, value: '1', score: 1, error: null },
          { dimension: '接管率占比', round: undefined, value: '1', score: 1, error: null },
          { dimension: '逐轮话轮评估', round: 1, value: '—', score: 0, error: null },
        ])
      )
    })

    it('无结果行（未完成/秒败）→ 单个「指标」Tab、无结果音频', () => {
      const detail = caseDetailFromDto(
        { ...detailDto, algorithm_results: [], audio_list: [] },
        []
      )
      expect(detail.devices.map((d) => d.deviceName)).toEqual(['pura90小艺'])
      expect(detail.devices[0].executionStatus).toBeNull()
      expect(detail.roundTabs.map((t) => [t.key, t.rows])).toEqual([['all', []]])
      expect(detail.resultAudios).toEqual([])
      expect(detail.resultAudioFields).toEqual([])
      expect(detail.results).toEqual([])
    })

    it('结果音频：result_audios 单独成块（按设备分组、无轮次）；audio_file 字段单独成集（带轮次）', () => {
      const detail = caseDetailFromDto(detailDto, results)
      // 本用例 result_audios 为空 → 「结果音频」块无内容
      expect(detail.resultAudios).toEqual([])
      // algorithm_results 的 audio_file 项是「执行结果字段」：label 去 @round 内部后缀、带 1 起轮次
      expect(detail.resultAudioFields).toEqual([
        {
          paramCode: 'user_wav@round:1',
          label: 'user_wav',
          round: 1,
          overall: false,
          dimensionName: null,
          deviceName: 'pura90小艺',
          url: null,
          path: 'case_pcm/402/xxx/r0_in.wav',
        },
        {
          paramCode: 'ai_wav@round:1',
          label: 'ai_wav',
          round: 1,
          overall: false,
          dimensionName: null,
          deviceName: 'pura90小艺',
          url: null,
          path: 'case_pcm/402/xxx/r0_out.wav',
        },
      ])
      expect(detail.referenceAudios).toEqual([
        {
          audioName: 'JG0006_输入.wav',
          deviceName: null,
          audioId: 1622,
          round: null,
          url: '/api/v1/audios/1622/stream',
          path: null,
        },
      ])
    })

    it('result_audios：设备键还原可读设备名；行名 filename → param_code → 「音频N」', () => {
      const detail = caseDetailFromDto(
        {
          ...detailDto,
          result_audios: {
            '9': [
              { url: '/a.wav', filename: 'out.wav' },
              { url: null, param_code: 'ai_wav' },
              { url: null },
            ],
            '9-pura90小艺-1.0.0': [{ url: '/b.wav', filename: 'b.wav' }],
          },
        },
        results
      )
      expect(detail.resultAudios).toEqual([
        { audioName: 'out.wav', deviceName: 'pura90小艺', round: null, url: '/a.wav', path: null },
        { audioName: 'ai_wav', deviceName: 'pura90小艺', round: null, url: null, path: null },
        { audioName: '音频3', deviceName: 'pura90小艺', round: null, url: null, path: null },
        { audioName: 'b.wav', deviceName: 'pura90小艺', round: null, url: '/b.wav', path: null },
      ])
    })

    it('audio_file 字段：@overall 后缀 → overall 标记；无后缀时回退 round_number', () => {
      const detail = caseDetailFromDto(
        {
          ...detailDto,
          algorithm_results: [
            {
              param_code: 'summary_wav@overall',
              param_type: 'audio_file',
              value: 'p/overall.wav',
              dimension_name: '接管率占比',
              device: '9-pura90小艺-1.0.0',
            },
            { param_code: 'plain_wav', param_type: 'audio_file', round_number: 2, value: 'p/r2.wav' },
          ],
        },
        results
      )
      expect(detail.resultAudioFields).toEqual([
        {
          paramCode: 'summary_wav@overall',
          label: 'summary_wav',
          round: null,
          overall: true,
          dimensionName: '接管率占比',
          deviceName: 'pura90小艺',
          url: null,
          path: 'p/overall.wav',
        },
        {
          paramCode: 'plain_wav',
          label: 'plain_wav',
          round: 2,
          overall: false,
          dimensionName: null,
          deviceName: null,
          url: null,
          path: 'p/r2.wav',
        },
      ])
    })
  })

  /**
   * INT-1688 返工：多轮夹具（真实库任务 402 / 用例 d8bdd5a6（DD139 多次打断）形态，
   * 7 轮 + 整体；维度逐轮 0..6、整体 null）。验轮次 Tab 装配与按轮出值。
   */
  describe('INT-1688 返工：多轮轮次 Tab（7 轮 + 整体）', () => {
    const multiDto: CaseDetailDto = {
      test_case_id: 'd8bdd5a6-666d-41ab-a366-6b9f3b27e564',
      task_id: 402,
      case_name: '测试用例_DD139_多次打断',
      execution_status: 'completed',
      evaluation_status: 'completed',
      duration: null,
      score: null,
      algorithm_type: 'voice_llm',
      devices: ['pura90小艺'],
      metric_configs: [
        { code: '合成成功率', name: '合成成功率' },
        { code: '打断识别率', name: '打断识别率' },
      ],
      algorithm_results: [1, 2, 3, 4, 5, 6, 7].map((round) => ({
        param_code: `user_wav@round:${round}`,
        param_type: 'audio_file',
        label: `user_wav (第${round}轮)`,
        round_number: round,
        value: `case_pcm/402/dd/r${round - 1}_in.wav`,
      })),
      audio_list: [1, 2, 3, 4, 5, 6, 7].map((round) => ({
        id: 1700 + round,
        filename: `DD139_第${round}轮.wav`,
        roundNumber: round,
      })),
    }
    const dims = (roundNumber: number | null): CaseResultDimension[] => [
      {
        dimensionId: 57,
        name: '合成成功率',
        value: roundNumber == null ? 5 : (roundNumber + 1) / 10,
        score: null,
        status: 'completed',
        evaluationStatus: 'completed',
        errorMessage: null,
        roundNumber,
      },
      {
        dimensionId: 58,
        name: '打断识别率',
        value: roundNumber == null ? 0.75 : (roundNumber + 1) / 100,
        score: null,
        status: 'completed',
        evaluationStatus: 'completed',
        errorMessage: null,
        roundNumber,
      },
    ]
    const multiResults: CaseResultForReview[] = [
      {
        id: 4114,
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
        dimensions: [...dims(null), ...[0, 1, 2, 3, 4, 5, 6].flatMap((rn) => dims(rn))],
      },
    ]

    it('第1轮…第7轮 + 整体，共 8 个 Tab；每 Tab 行=指标、列=设备、逐轮出值', () => {
      const detail = caseDetailFromDto(multiDto, multiResults)
      expect(detail.roundTabs.map((t) => t.label)).toEqual([
        '第1轮',
        '第2轮',
        '第3轮',
        '第4轮',
        '第5轮',
        '第6轮',
        '第7轮',
        '整体',
      ])
      expect(detail.roundTabs[0].rows).toEqual([
        { dimension: '合成成功率', values: { pura90小艺: '0.1' } },
        { dimension: '打断识别率', values: { pura90小艺: '0.01' } },
      ])
      expect(detail.roundTabs[6].rows).toEqual([
        { dimension: '合成成功率', values: { pura90小艺: '0.7' } },
        { dimension: '打断识别率', values: { pura90小艺: '0.07' } },
      ])
      expect(detail.roundTabs[7].rows).toEqual([
        { dimension: '合成成功率', values: { pura90小艺: '5' } },
        { dimension: '打断识别率', values: { pura90小艺: '0.75' } },
      ])
    })

    it('执行结果音频字段带 1 起轮次（供按 Tab 过滤）；参考音频同样带轮次', () => {
      const detail = caseDetailFromDto(multiDto, multiResults)
      expect(detail.resultAudios).toEqual([])
      expect(detail.resultAudioFields.map((a) => [a.label, a.round])).toEqual([
        ['user_wav', 1],
        ['user_wav', 2],
        ['user_wav', 3],
        ['user_wav', 4],
        ['user_wav', 5],
        ['user_wav', 6],
        ['user_wav', 7],
      ])
      expect(detail.referenceAudios.map((a) => a.round)).toEqual([1, 2, 3, 4, 5, 6, 7])
    })

    it('整体无评估值 → 不出现「整体」Tab（照 V9.7.10 tabHasMetricData）', () => {
      const detail = caseDetailFromDto(multiDto, [
        {
          ...multiResults[0],
          dimensions: [0, 1, 2, 3, 4, 5, 6].flatMap((rn) => dims(rn)),
        },
      ])
      expect(detail.roundTabs.map((t) => t.key)).toEqual([
        'round:1',
        'round:2',
        'round:3',
        'round:4',
        'round:5',
        'round:6',
        'round:7',
      ])
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
