/**
 * INT-289：Device 列表获取失败路径——失败不清空既有列表（保留旧数据）+ 错误条状态置位。
 *
 * 旧实现：devicesPort.getAll / apisPort.getAll / audiosPort.getAll / playbackPort.getAll
 *   任一分区失败即 console.error 后清空对应数组（testDevices.value = [] 等），
 *   全页无错误提示、旧数据被误清。
 *
 * 锁定契约：
 * 1. 测试设备分区失败：testDevices 保留旧数据，error 置位并含分区名；
 * 2. 播放设备失败：playbackDevices 保留旧数据；
 * 3. 多分区失败：error 汇总各失败分区名；
 * 4. 全部成功：error 保持 null；
 * 5. 外层兜底 catch 仍置位 error。
 *
 * 说明：deviceState 为真实模块（模块级 ref 可跨用例共享），仅替身各 Port。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const ports = vi.hoisted(() => ({
  getTest: vi.fn(),
  getApi: vi.fn(),
  getPrompt: vi.fn(),
  getPlayback: vi.fn(),
}))

vi.mock('@/composables/device/devicesPort', () => ({
  devicesPort: { getAll: ports.getTest },
  BATCH_LIST_PARAMS: {},
}))
vi.mock('@/composables/device/playbackPort', () => ({
  playbackPort: { getAll: ports.getPlayback },
}))
vi.mock('@/composables/apiTest/apisPort', () => ({
  apisPort: { getAll: ports.getApi },
}))
vi.mock('@/composables/audio/audiosPort', () => ({
  audiosPort: { getAll: ports.getPrompt },
}))

import { fetchAllDevices } from '../deviceFetching'
import { testDevices, apiDevices, playbackDevices, promptAudios, loading, error, isHealthChecking, setDeviceManagement } from '../deviceState'

beforeEach(() => {
  vi.clearAllMocks()
  loading.value = false
  error.value = null
  testDevices.value = []
  apiDevices.value = []
  playbackDevices.value = []
  promptAudios.value = []
  isHealthChecking.value = true // 跳过 autoHealthCheck 副作用
  setDeviceManagement({ devices: ref<any[]>([]) } as any)
  ports.getTest.mockResolvedValue([])
  ports.getApi.mockResolvedValue([])
  ports.getPrompt.mockResolvedValue({ items: [] })
  ports.getPlayback.mockResolvedValue([])
})

describe('fetchAllDevices 失败保留旧数据（INT-289）', () => {
  it('测试设备分区失败：testDevices 保留旧数据，error 置位含分区名', async () => {
    testDevices.value = [{ id: 1, name: '旧测试设备' }]
    ports.getTest.mockRejectedValue(new Error('网络断开'))
    ports.getPlayback.mockResolvedValue([])

    await fetchAllDevices()

    expect(testDevices.value).toEqual([{ id: 1, name: '旧测试设备' }])
    expect(error.value).toContain('测试设备')
    expect(error.value).toContain('保留现有数据')
  })

  it('播放设备失败：playbackDevices 保留旧数据并计入 error', async () => {
    playbackDevices.value = [{ id: 9, name: '旧播放设备' }]
    ports.getPlayback.mockRejectedValue(new Error('后端停服'))

    await fetchAllDevices()

    expect(playbackDevices.value).toEqual([{ id: 9, name: '旧播放设备' }])
    expect(error.value).toContain('播放设备')
  })

  it('多分区失败：error 汇总各失败分区名', async () => {
    ports.getTest.mockRejectedValue(new Error('t'))
    ports.getApi.mockRejectedValue(new Error('a'))
    ports.getPrompt.mockRejectedValue(new Error('p'))
    ports.getPlayback.mockRejectedValue(new Error('pb'))

    await fetchAllDevices()

    expect(error.value).toContain('测试设备')
    expect(error.value).toContain('API设备')
    expect(error.value).toContain('提示词音频')
    expect(error.value).toContain('播放设备')
  })

  it('全部成功：error 保持 null，数据完成同步', async () => {
    ports.getTest.mockResolvedValue([{ id: 1, name: 't1', status: 'online', category: '测试设备' }])
    ports.getApi.mockResolvedValue([{ id: 2, name: 'a1', endpoints: [] }])
    ports.getPrompt.mockResolvedValue({ items: [{ id: 3, name: 'p1' }] })
    ports.getPlayback.mockResolvedValue([{ id: 4, name: 'pb1' }])

    await fetchAllDevices()

    expect(error.value).toBeNull()
    expect(testDevices.value.length).toBe(1)
    expect(apiDevices.value.length).toBe(1)
    expect(promptAudios.value.length).toBe(1)
    expect(playbackDevices.value.length).toBe(1)
  })
})
