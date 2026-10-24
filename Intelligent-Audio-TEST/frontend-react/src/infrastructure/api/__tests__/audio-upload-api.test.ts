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
