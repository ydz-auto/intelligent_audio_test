/**
 * 音频试听配置弹窗测试（11_用例域.md §5.2）：
 * 播放模式 RadioGroup + 偏移量 →「开始试听」切音频播放器 stage
 * （进度条/播放暂停/停止/播放设备区），「返回试听配置」双向切换。
 * INT-1424：试听链路接真实音频流——播放器在未传 audioItem 时禁用播放
 * （无真实音频 id 无法取流），配置流程与双向切换不变。
 * 终审 P2-2：实验室播放必须把用例配置的播放设备（playback_device_ids /
 * device_unique_ids）带给后端，设备不能只停在 UI 文案上。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TestCaseListItem } from '@/domain/models/testCase'
import { AudioPreviewConfigDialog } from '@/features/testcases/modals/audio-preview-config-dialog'

const previewMock = vi.fn()
const stopPreviewMock = vi.fn()
const streamMock = vi.fn()

vi.mock('@/infrastructure/api/audios-api', () => ({
  preview: (...args: unknown[]) => previewMock(...args),
  stopPreview: (...args: unknown[]) => stopPreviewMock(...args),
  stream: (...args: unknown[]) => streamMock(...args),
  fetchAudioDuration: () => Promise.resolve(null),
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
}

const setupUser = () => userEvent.setup()

beforeEach(() => {
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

  it('§5.2 开始试听 → 音频播放器（标题/进度/播放暂停/停止/播放设备区）', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
        audioItem={{ id: 42, name: 'sample.wav', spl: 65, deviceLabels: ['音频接口 A (通道 1) [干声]'] }}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    expect(
      screen.getByText(`测试用例预览｜sample.wav 音频`)
    ).toBeInTheDocument()
    expect(screen.getByLabelText('播放进度')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '播放' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
    expect(screen.getByText('播放设备（浏览器播放）')).toBeInTheDocument()
    expect(screen.getByText('音频接口 A (通道 1) [干声]')).toBeInTheDocument()
  })

  it('§5.2 未传音频对象时播放钮禁用（无真实音频 id 无法取流）', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    expect(screen.getByRole('button', { name: '播放' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '停止' })).toBeEnabled()
  })

  it('§5.2 播放器「返回试听配置」双向切换回配置态', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
      />
    )
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await user.click(screen.getByRole('button', { name: '返回试听配置' }))
    expect(screen.getByText('音频试听配置')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始试听' })).toBeInTheDocument()
  })

  it('P2-2 实验室播放：按用例配置的播放设备发送 playback_device_ids / device_unique_ids', async () => {
    const user = setupUser()
    render(
      <AudioPreviewConfigDialog
        open
        onOpenChange={vi.fn()}
        caseItem={CASE_ITEM}
        audioItem={{
          id: 42,
          name: 'sample.wav',
          spl: 65,
          duration: 3,
          deviceLabels: ['音频接口 A (通道 1)'],
          deviceIds: ['7'],
        }}
      />
    )
    await user.click(screen.getByText('实验室播放'))
    await user.click(screen.getByRole('button', { name: '开始试听' }))
    await user.click(screen.getByRole('button', { name: '播放' }))

    expect(previewMock).toHaveBeenCalledWith(42, {
      playbackDeviceId: 7,
      playbackDeviceIds: [7],
      deviceUniqueIds: ['uid-7'],
      spl: 65,
      offset: undefined,
    })
  })
})
