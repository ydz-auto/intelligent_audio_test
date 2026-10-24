/**
 * 音频试听配置弹窗测试（11_用例域.md §5.2）：
 * 播放模式 RadioGroup + 偏移量 →「开始试听」进音频播放器（进度/播放暂停/停止/真实设备区），
 * 「返回试听配置」双向切换。两个试听源（INT-1534 返工并线）：
 * - 用例源（未带 audioItem）：POST /testcases/{id}/preview（offset+preview_type+playback_mode），
 *   播放器按响应 audio_stream_urls 多轮连播、设备取用例 config；
 * - 音频库/全局噪声源（带 audioItem，INT-1424）：播放器自己 GET /audios/{id}/stream /
 *   POST /audios/{id}/preview|stop-preview，实验室播放带 playback_device_ids + device_unique_ids。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TestCaseListItem, TestCasePreview } from '@/domain/models/testCase'
import { ApiError } from '@/infrastructure/api/api-error'
import { AudioPreviewConfigDialog } from '@/features/testcases/modals/audio-preview-config-dialog'

const previewTestCaseMock = vi.hoisted(() => vi.fn())
const stopTestCasePreviewMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/testcases-api', () => ({
  previewTestCase: previewTestCaseMock,
  stopTestCasePreview: stopTestCasePreviewMock,
}))

const previewMock = vi.hoisted(() => vi.fn())
const stopPreviewMock = vi.hoisted(() => vi.fn())
const streamMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/audios-api', () => ({
  preview: previewMock,
  stopPreview: stopPreviewMock,
  stream: streamMock,
  fetchAudioDuration: () => Promise.resolve(null),
}))

const toastErrorMock = vi.hoisted(() => vi.fn())
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: toastErrorMock },
}))

// 播放设备查表（真实 /playback-devices 的 application hook）
vi.mock('@/application/devices/use-devices', () => ({
  usePlaybackDevices: () => ({
    data: [
      {
        id: 7,
        name: '音频接口 A',
        channelIndex: 1,
        deviceType: 'dry',
        deviceUniqueId: 'uid-7',
      },
    ],
    isLoading: false,
  }),
}))

const FRONTEND_PREVIEW: TestCasePreview = {
  testCaseId: 'tc-001',
  previewTaskId: null,
  status: 'frontend_preview_ready',
  message: '前端播放模式，返回音频流URL',
  duration: 12,
  playbackMode: 'frontend',
  audioId: 2338,
  audioStreamUrl: '/api/v1/audios/download?path=test_data/dry/a.wav',
  audioStreamUrls: ['/api/v1/audios/download?path=test_data/dry/a.wav'],
}

const CASE_ITEM: TestCaseListItem = {
  id: 'tc-001',
  name: '智能音箱-播放音乐-中文-客厅',
  description: '客厅环境播放中文音乐',
  groupId: 'g1',
  groupName: '智能音箱功能测试',
  type: 'e2e',
  tags: ['音箱'],
  algorithmType: 'asr-v3',
  createdAt: '2026-09-10 10:00',
  updatedAt: '2026-10-15 09:32',
  isFavorite: false,
  deleted: false,
  deletedAt: null,
  deletedByUserId: null,
  totalDuration: 156,
  rounds: 2,
  config: {
    rounds: [
      {
        round_number: 1,
        audios: [
          {
            audio_id: 2338,
            audio_name: '客厅音乐.wav',
            playback_device_id: 10,
            playback_device_name: '实验室音箱 A',
          },
        ],
      },
    ],
  },
}

const AUDIO_ITEM = {
  id: 42,
  name: 'sample.wav',
  spl: 65,
  duration: 3,
  deviceLabels: ['音频接口 A (通道 1)'],
  deviceIds: ['7'],
}

const setupUser = () => userEvent.setup()

beforeEach(() => {
  previewTestCaseMock.mockReset()
  stopTestCasePreviewMock.mockReset().mockResolvedValue(undefined)
  toastErrorMock.mockReset()
  previewMock.mockReset().mockResolvedValue({ success: true })
  stopPreviewMock.mockReset().mockResolvedValue({ success: true })
  streamMock.mockReset().mockResolvedValue('http://stream.local/a.wav')
})

describe('AudioPreviewConfigDialog', () => {
  it('§5.2 试听配置：浏览器/实验室两种播放模式 + 偏移量输入', () => {
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    expect(screen.getByText('音频试听配置')).toBeInTheDocument()
    expect(screen.getByText('浏览器播放')).toBeInTheDocument()
    expect(screen.getByText('实验室播放')).toBeInTheDocument()
    expect(screen.getByLabelText('偏移量秒数')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始试听' })).toBeInTheDocument()
  })

  it('用例源：开始试听 → 真实 preview 请求（offset+preview_type+playback_mode）→ 播放器', async () => {
    const user = setupUser()
    previewTestCaseMock.mockResolvedValue(FRONTEND_PREVIEW)
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.clear(screen.getByLabelText('偏移量秒数'))
    await user.type(screen.getByLabelText('偏移量秒数'), '3')
    await user.click(screen.getByRole('button', { name: '开始试听' }))

    expect(previewTestCaseMock).toHaveBeenCalledWith('tc-001', {
      offset: 3,
      previewType: 'frontend',
      playbackMode: 'frontend',
    })
    await waitFor(() =>
      expect(
        screen.getByText(`测试用例预览｜${CASE_ITEM.name} 音频`)
      ).toBeInTheDocument()
    )
    expect(screen.getByLabelText('播放进度')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
    // 浏览器播放：真实流地址进 <audio>
    expect(screen.getByTestId('case-preview-audio')).toHaveAttribute(
      'src',
      FRONTEND_PREVIEW.audioStreamUrl
    )
    expect(screen.getByText('播放设备（浏览器播放）')).toBeInTheDocument()
    expect(screen.getByText('本机扬声器直接输出')).toBeInTheDocument()
    // 进播放器即起播（按钮呈暂停态），可切暂停/继续
    expect(screen.getByRole('button', { name: '暂停' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '暂停' }))
    expect(screen.getByRole('button', { name: '播放' })).toBeInTheDocument()
  })

  it('用例源 P3-2：多轮预览按 preview 总时长显示进度与轮次', async () => {
    const user = setupUser()
    previewTestCaseMock.mockResolvedValue({
      ...FRONTEND_PREVIEW,
      duration: 20,
      audioStreamUrls: [
        '/api/v1/audios/download?path=test_data/dry/a.wav',
        '/api/v1/audios/download?path=test_data/dry/b.wav',
      ],
    })
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await waitFor(() =>
      expect(screen.getByTestId('player-time')).toHaveTextContent(
        '00:00 / 00:20 · 第 1/2 轮'
      )
    )
  })

  it('用例源实验室播放：preview_type=backend + 设备区取用例配置真实设备', async () => {
    const user = setupUser()
    previewTestCaseMock.mockResolvedValue({
      ...FRONTEND_PREVIEW,
      status: 'preview_started',
      playbackMode: 'backend',
      audioStreamUrl: null,
      audioStreamUrls: [],
      duration: 30,
    })
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByText('实验室播放'))
    await user.click(screen.getByRole('button', { name: '开始试听' }))

    expect(previewTestCaseMock).toHaveBeenCalledWith('tc-001', {
      offset: 0,
      previewType: 'backend',
      playbackMode: 'backend',
    })
    await waitFor(() =>
      expect(screen.getByText('播放设备（实验室播放）')).toBeInTheDocument()
    )
    expect(screen.getByText('实验室音箱 A')).toBeInTheDocument()
    // 实验室播放不发音频流，不渲染 <audio>
    expect(screen.queryByTestId('case-preview-audio')).not.toBeInTheDocument()
    expect(screen.getByText(/00:00 \/ 00:30/)).toBeInTheDocument()
  })

  it('用例源试听失败 → toast「音频试听失败: …」+ 停在配置态可重试', async () => {
    const user = setupUser()
    previewTestCaseMock.mockRejectedValue(
      new ApiError({ message: '用例未配置任何音频资源，无法预览' })
    )
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))

    await waitFor(() =>
      expect(
        screen.getByText('用例未配置任何音频资源，无法预览')
      ).toBeInTheDocument()
    )
    expect(toastErrorMock).toHaveBeenCalledWith(
      '音频试听失败: 用例未配置任何音频资源，无法预览'
    )
    // 仍在配置态（未进播放器），可再次点开始试听
    expect(screen.getByRole('button', { name: '开始试听' })).toBeInTheDocument()
    expect(screen.queryByLabelText('播放进度')).not.toBeInTheDocument()
  })

  it('用例源 P3-1：请求未返回即关闭弹窗 → 响应到达后不回到播放器', async () => {
    const user = setupUser()
    let resolvePreview: ((value: TestCasePreview) => void) | undefined
    previewTestCaseMock.mockImplementation(
      () =>
        new Promise<TestCasePreview>((resolve) => {
          resolvePreview = resolve
        })
    )
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await user.click(screen.getByRole('button', { name: '取消' }))
    // 关闭后才返回的响应必须被丢弃
    resolvePreview?.(FRONTEND_PREVIEW)
    await waitFor(() =>
      expect(screen.getByText('音频试听配置')).toBeInTheDocument()
    )
    expect(screen.queryByLabelText('播放进度')).not.toBeInTheDocument()
  })

  it('用例源实验室播放器「返回试听配置」→ 停设备放音 + 回配置态', async () => {
    const user = setupUser()
    previewTestCaseMock.mockResolvedValue({
      ...FRONTEND_PREVIEW,
      playbackMode: 'backend',
      audioStreamUrl: null,
      audioStreamUrls: [],
      duration: 30,
    })
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByText('实验室播放'))
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await waitFor(() =>
      expect(screen.getByText('实验室音箱 A')).toBeInTheDocument()
    )
    await user.click(screen.getByRole('button', { name: '返回试听配置' }))
    expect(stopTestCasePreviewMock).toHaveBeenCalledWith('tc-001')
    // 只停一次：卸载 cleanup 不得再补一次 stop_preview（INT-1534 P3-1）
    expect(stopTestCasePreviewMock).toHaveBeenCalledTimes(1)
    expect(screen.getByText('音频试听配置')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始试听' })).toBeInTheDocument()
  })

  it('音频库源：开始试听直接进播放器，播放器取真实音频流', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={null}
        audioItem={AUDIO_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    expect(
      screen.getByText('测试用例预览｜sample.wav 音频')
    ).toBeInTheDocument()
    // 音频库源不调用用例试听接口
    expect(previewTestCaseMock).not.toHaveBeenCalled()
    await waitFor(() => expect(streamMock).toHaveBeenCalledWith(42))
    expect(screen.getByText('音频接口 A (通道 1)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '播放' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeEnabled()
  })

  it('音频库源 P2-2：实验室播放按设备记录发送 playback_device_ids / device_unique_ids', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={null}
        audioItem={AUDIO_ITEM}
      />
    )
    await user.click(screen.getByText('实验室播放'))
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await user.click(screen.getByRole('button', { name: '播放' }))

    await waitFor(() =>
      expect(previewMock).toHaveBeenCalledWith(42, {
        playbackDeviceId: 7,
        playbackDeviceIds: [7],
        deviceUniqueIds: ['uid-7'],
        spl: 65,
        offset: undefined,
      })
    )
  })

  it('音频库源 P2：偏移量进 startOffset，实验室播放请求带 offset + 进度起点跟随', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={null}
        audioItem={{ ...AUDIO_ITEM, duration: 30 }}
      />
    )
    await user.click(screen.getByText('实验室播放'))
    const offsetInput = screen.getByLabelText('偏移量秒数')
    await user.clear(offsetInput)
    await user.type(offsetInput, '5')
    await user.click(screen.getByRole('button', { name: '开始试听' }))

    // 进播放器后起点即 5s（不再是恒 0）
    expect(screen.getByTestId('player-time')).toHaveTextContent('00:05 / 00:30')

    await user.click(screen.getByRole('button', { name: '播放' }))
    await waitFor(() =>
      expect(previewMock).toHaveBeenCalledWith(42, {
        playbackDeviceId: 7,
        playbackDeviceIds: [7],
        deviceUniqueIds: ['uid-7'],
        spl: 65,
        offset: 5,
      })
    )
  })

  it('音频库源：偏移量为负 → 错误条 + 停在配置态，不发请求', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={null}
        audioItem={AUDIO_ITEM}
      />
    )
    fireEvent.change(screen.getByLabelText('偏移量秒数'), {
      target: { value: '-2' },
    })
    await user.click(screen.getByRole('button', { name: '开始试听' }))

    expect(screen.getByText('偏移量需为不小于 0 的秒数')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始试听' })).toBeInTheDocument()
    expect(screen.queryByLabelText('播放进度')).not.toBeInTheDocument()
    expect(previewMock).not.toHaveBeenCalled()
    expect(streamMock).not.toHaveBeenCalled()
  })

  it('音频库源 P2：实验室暂停先等 stop-preview 完成再接续播', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={null}
        audioItem={AUDIO_ITEM}
      />
    )
    await user.click(screen.getByText('实验室播放'))
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await user.click(screen.getByRole('button', { name: '播放' }))
    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1))

    await user.click(screen.getByRole('button', { name: '暂停' }))
    await waitFor(() => expect(stopPreviewMock).toHaveBeenCalledWith(42))
    await user.click(screen.getByRole('button', { name: '播放' }))
    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(2))
    // stop → preview 串行：暂停的停止请求必须在续播请求之前完成
    expect(stopPreviewMock.mock.invocationCallOrder[0]).toBeLessThan(
      previewMock.mock.invocationCallOrder[1]
    )
  })
})
