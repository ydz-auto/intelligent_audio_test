/**
 * 音频上传 merge 载荷单测（INT-1613，§5.7.6/§5.7.7）：
 * 整组 rounds 原样提交并把 round_number 归一为 1..N；播放设备写进每轮 audios[].playback_device_id，
 * 顶层发 default_playback_device_id（建用例链路唯一消费的兜底键）；缺省时按当前文件单轮。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  mergeChunks,
  type UploadTestCaseConfig,
} from '@/infrastructure/api/audio-upload-api'

const postMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/client', () => ({
  apiClient: { post: postMock },
}))

function baseConfig(overrides: Partial<UploadTestCaseConfig> = {}): UploadTestCaseConfig {
  return {
    createTestCase: true,
    algorithmType: 'voice_llm',
    algorithmParams: [],
    dimensions: [],
    playbackDeviceId: 12,
    spl: 65,
    noiseAudioId: null,
    noiseSpl: 60,
    inheritTags: true,
    groupName: undefined,
    tags: [],
    audioType: 'dry',
    ...overrides,
  }
}

describe('mergeChunks（上传合并载荷）', () => {
  beforeEach(() => {
    postMock.mockReset()
    postMock.mockResolvedValue({ audio_id: 7, name: 'b.wav', test_case_id: 'tc1', test_case_count: 1 })
  })

  it('无分组轮次 → 当前文件单轮（round_number 1 / play_order 1）', async () => {
    await mergeChunks('task-1', 'file-1', 'a.wav', baseConfig())
    const payload = postMock.mock.calls[0][1]
    expect(payload.test_case_config.rounds).toEqual([
      { round_number: 1, audios: [{ audio_name: 'a.wav', play_order: 1, playback_device_id: 12 }] },
    ])
    expect(payload.default_playback_device_id).toBe(12)
    expect(payload).not.toHaveProperty('playback_device_id')
  })

  it('整组 rounds → 原样提交、round_number 归一到 1..N、每轮音频写 playback_device_id', async () => {
    const rounds = [
      { round_number: 9, audios: [{ audio_name: 'a.wav', play_order: 1, audio_id: 5 }] },
      { round_number: 2, audios: [{ audio_name: 'b.wav', play_order: 1, spl: 70 }] },
      { round_number: 1, audios: [{ audio_name: 'c.wav', play_order: 1 }] },
    ]
    await mergeChunks('task-1', 'file-3', 'c.wav', baseConfig({ rounds }))
    const sent = postMock.mock.calls[0][1].test_case_config.rounds
    expect(sent.map((r: { round_number: number }) => r.round_number)).toEqual([1, 2, 3])
    expect(sent[0].audios[0]).toEqual({
      audio_name: 'a.wav',
      play_order: 1,
      audio_id: 5,
      playback_device_id: 12,
    })
    // JSON 里已有的 spl 保留
    expect(sent[1].audios[0].spl).toBe(70)
  })

  it('未选播放设备 → 不写逐轮设备值', async () => {
    await mergeChunks(
      'task-1',
      'file-1',
      'a.wav',
      baseConfig({
        playbackDeviceId: null,
        rounds: [{ round_number: 1, audios: [{ audio_name: 'a.wav', play_order: 1 }] }],
      })
    )
    const payload = postMock.mock.calls[0][1]
    expect(payload.default_playback_device_id).toBeNull()
    expect(payload.test_case_config.rounds[0].audios[0]).toEqual({
      audio_name: 'a.wav',
      play_order: 1,
    })
  })

  it('返回值带 audioName（组内回填 audio_id 的匹配键）', async () => {
    await expect(mergeChunks('task-1', 'file-1', 'a.wav', baseConfig())).resolves.toEqual({
      audioId: 7,
      audioName: 'b.wav',
      testCaseId: 'tc1',
      testCaseCount: 1,
    })
  })
})

/**
 * §5.7.3 / §5.7.4 / §5.7.7 三档轮次范围载荷（INT-1614）：
 * 设备逐轮写 rounds[].audios[].playback_device_id；维度逐轮写 rounds[].evaluation.dimensions；
 * 顶层 dimensions 在「所有轮次」档放 single+multi、「指定/逐轮」档只放 multi（条目必带 name）。
 */
describe('mergeChunks（三档轮次范围载荷）', () => {
  const dims = [
    { id: 3, name: '识别准确率', weight: 50, round_scope: 'single' as const },
    { id: 4, name: '唤醒成功率', round_scope: 'single' as const },
  ]
  const multi = [{ id: 7, name: '对话连贯性', round_scope: 'multi' as const }]
  const rounds = [
    { round_number: 1, audios: [{ audio_name: 'a.wav', play_order: 1 }] },
    { round_number: 2, audios: [{ audio_name: 'b.wav', play_order: 1 }] },
    { round_number: 3, audios: [{ audio_name: 'c.wav', play_order: 1 }] },
  ]

  beforeEach(() => {
    postMock.mockReset()
    postMock.mockResolvedValue({ audio_id: 7, name: 'c.wav', test_case_id: 'tc1', test_case_count: 1 })
  })

  it('所有轮次：各轮同一设备、顶层放 single+multi、轮内不写 evaluation', async () => {
    await mergeChunks('task-1', 'file-3', 'c.wav', baseConfig({
      rounds,
      dimensions: dims,
      multiDimensions: multi,
      playbackDeviceId: 12,
      dimensionPlan: { mode: 'all', uniformIds: [3, 4], specificRounds: [1], perRoundIds: {} },
      devicePlan: { mode: 'all', uniformId: 12, specificRounds: [1], perRoundIds: {} },
    }))
    const payload = postMock.mock.calls[0][1]
    expect(payload.default_playback_device_id).toBe(12)
    expect(
      payload.test_case_config.rounds.map(
        (r: { audios: Array<{ playback_device_id?: number }> }) => r.audios[0].playback_device_id
      )
    ).toEqual([12, 12, 12])
    expect(payload.test_case_config.rounds[0]).not.toHaveProperty('evaluation')
    expect(payload.dimensions).toEqual([...dims, ...multi])
  })

  it('指定轮次：只有勾中轮写设备与维度，未勾中轮写空维度，顶层只放 multi', async () => {
    await mergeChunks('task-1', 'file-3', 'c.wav', baseConfig({
      rounds,
      dimensions: dims,
      multiDimensions: multi,
      playbackDeviceId: 12,
      dimensionPlan: { mode: 'specific', uniformIds: [3], specificRounds: [2], perRoundIds: {} },
      devicePlan: { mode: 'specific', uniformId: 12, specificRounds: [2], perRoundIds: {} },
    }))
    const payload = postMock.mock.calls[0][1]
    const sent = payload.test_case_config.rounds
    expect(sent[0].audios[0]).not.toHaveProperty('playback_device_id')
    expect(sent[1].audios[0].playback_device_id).toBe(12)
    expect(sent[2].audios[0]).not.toHaveProperty('playback_device_id')
    expect(sent[0].evaluation).toEqual({ dimensions: [] })
    expect(sent[1].evaluation).toEqual({ dimensions: [dims[0]] })
    expect(sent[2].evaluation).toEqual({ dimensions: [] })
    expect(payload.dimensions).toEqual(multi)
  })

  it('逐轮设置：各轮各自设备与维度，未设置轮不写设备', async () => {
    await mergeChunks('task-1', 'file-3', 'c.wav', baseConfig({
      rounds,
      dimensions: dims,
      multiDimensions: multi,
      playbackDeviceId: 12,
      dimensionPlan: {
        mode: 'per_round',
        uniformIds: [],
        specificRounds: [1],
        perRoundIds: { 1: [3], 2: [4], 3: [] },
      },
      devicePlan: {
        mode: 'per_round',
        uniformId: null,
        specificRounds: [1],
        perRoundIds: { 1: 12, 2: 13 },
      },
    }))
    const payload = postMock.mock.calls[0][1]
    const sent = payload.test_case_config.rounds
    expect(sent[0].audios[0].playback_device_id).toBe(12)
    expect(sent[1].audios[0].playback_device_id).toBe(13)
    expect(sent[2].audios[0]).not.toHaveProperty('playback_device_id')
    expect(sent[0].evaluation).toEqual({ dimensions: [dims[0]] })
    expect(sent[1].evaluation).toEqual({ dimensions: [dims[1]] })
    expect(sent[2].evaluation).toEqual({ dimensions: [] })
    expect(payload.dimensions).toEqual(multi)
  })

  it('多轮整体维度条目带 name（读侧 TestCaseDimensionItem.name 必填，审计 P3-2）', async () => {
    await mergeChunks('task-1', 'file-1', 'a.wav', baseConfig({
      dimensions: [],
      multiDimensions: multi,
    }))
    const payload = postMock.mock.calls[0][1]
    expect(payload.dimensions).toEqual([{ id: 7, name: '对话连贯性', round_scope: 'multi' }])
  })

  it('「逐轮设置」切回「所有轮次」：顶层只发当前统一集，逐轮档残留值不得混入（审计 P2-1）', async () => {
    // catalog 里带着逐轮档的旧值（4），统一集只有新选的 3
    const staleDims = [...dims, { id: 9, name: '逐轮三分类评估', round_scope: 'single' as const }]
    await mergeChunks('task-1', 'file-3', 'c.wav', baseConfig({
      rounds,
      dimensions: staleDims,
      multiDimensions: multi,
      dimensionPlan: { mode: 'all', uniformIds: [3], specificRounds: [1], perRoundIds: { 1: [3, 4, 9] } },
      devicePlan: { mode: 'all', uniformId: 12, specificRounds: [1], perRoundIds: {} },
    }))
    const payload = postMock.mock.calls[0][1]
    expect(payload.dimensions).toEqual([dims[0], ...multi])
  })

  it('「所有轮次」档未选任何维度：顶层只有 multi，不带逐轮残留（审计 P2-1）', async () => {
    await mergeChunks('task-1', 'file-3', 'c.wav', baseConfig({
      rounds,
      dimensions: dims,
      multiDimensions: multi,
      dimensionPlan: { mode: 'all', uniformIds: [], specificRounds: [1], perRoundIds: { 1: [3, 4] } },
      devicePlan: { mode: 'all', uniformId: 12, specificRounds: [1], perRoundIds: {} },
    }))
    const payload = postMock.mock.calls[0][1]
    expect(payload.dimensions).toEqual(multi)
  })
})
