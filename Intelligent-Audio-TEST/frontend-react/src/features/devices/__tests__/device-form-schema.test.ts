import { describe, expect, it } from 'vitest'

import {
  apiDeviceFormSchema,
  playbackDeviceFormSchema,
  testDeviceFormSchema,
} from '@/features/devices/lib/device-form-schema'

describe('设备表单 schema（16_设备域.md §6.2 必填口径；AGENTS §3.7 RHF+zod）', () => {
  it('测试设备必填项缺失时校验失败（P2-11 返修）', () => {
    const result = testDeviceFormSchema.safeParse({
      name: '',
      description: '',
      remark: '',
      model: '',
      deviceType: 'physical',
      system: 'Android',
      systemVersion: '',
      apiLevel: '',
      appName: '',
      appVersion: '',
      connectionType: 'usb',
      serialNumber: '',
      ip: '',
      port: '5555',
      needsPromptAudio: false,
      algorithms: [],
      tags: [],
      priority: '5',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.map((i) => i.path[0])).toContain('name')
      expect(result.error.issues.map((i) => i.path[0])).toContain('model')
      expect(result.error.issues.map((i) => i.path[0])).toContain('systemVersion')
      expect(result.error.issues.map((i) => i.path[0])).toContain('serialNumber')
    }
  })

  it('播放设备必填项缺失时校验失败（设备类型/系统唯一标识/采样率）', () => {
    const result = playbackDeviceFormSchema.safeParse({
      name: '参考音源',
      description: '',
      model: 'Audio Gen Pro',
      deviceType: '',
      deviceUniqueId: '',
      channelIndex: '0',
      supportedChannels: '',
      supportedFormats: [],
      sampleRate: '',
      splMappingId: '',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path[0])
      expect(paths).toContain('deviceType')
      expect(paths).toContain('deviceUniqueId')
      expect(paths).toContain('sampleRate')
    }
  })

  it('API 必填项缺失时校验失败（API名称/协议/算法；INT-1223：Master URL 移除）', () => {
    const result = apiDeviceFormSchema.safeParse({
      name: '',
      description: '',
      vendor: '',
      protocol: '',
      environment: 'testing',
      algorithmType: '',
      maxProcess: '5',
      maxTimeout: '30',
      maxAudioDuration: '60',
    })
    expect(result.success).toBe(false)
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path[0])
      expect(paths).toContain('name')
      expect(paths).toContain('protocol')
      expect(paths).toContain('algorithmType')
    }
  })

  it('无 apiUrl 仅端点通过（INT-1223：Master URL 已移除，表单不含 apiUrl 校验通过）', () => {
    const result = apiDeviceFormSchema.safeParse({
      name: '语音识别 API',
      description: '',
      vendor: '',
      protocol: 'https',
      environment: 'testing',
      algorithmType: 'asr_streaming',
      maxProcess: '5',
      maxTimeout: '30',
      maxAudioDuration: '60',
    })
    expect(result.success).toBe(true)
  })

  it('合法提交通过校验', () => {
    expect(
      testDeviceFormSchema.safeParse({
        name: '音箱-客厅位',
        description: '',
        remark: '',
        model: '旗舰 S1',
        deviceType: 'physical',
        system: 'Android',
        systemVersion: '12',
        apiLevel: '',
        appName: '音乐播放器',
        appVersion: '2.4.0',
        connectionType: 'usb',
        serialNumber: 'SN-A001',
        ip: '',
        port: '5555',
        needsPromptAudio: false,
        algorithms: ['asr_streaming'],
        tags: [],
        priority: '5',
      }).success
    ).toBe(true)
  })

  describe('API 代理配置校验（INT-1029：proxy_type/proxy_url 契约 user:pass@host:port 不含 scheme）', () => {
    const baseApi = {
      name: '语音识别 API',
      description: '',
      vendor: '',
      protocol: 'https',
      environment: 'testing',
      algorithmType: 'asr_streaming',
      maxProcess: '5',
      maxTimeout: '30',
      maxAudioDuration: '60',
    }

    it('代理类型已选但代理地址为空 → 校验失败', () => {
      const result = apiDeviceFormSchema.safeParse({ ...baseApi, proxyType: 'http', proxyUrl: '' })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.map((i) => i.path[0])).toContain('proxyUrl')
      }
    })

    it('代理地址带 scheme 前缀 → 校验失败（INT-846 契约）', () => {
      const result = apiDeviceFormSchema.safeParse({
        ...baseApi,
        proxyType: 'socks5',
        proxyUrl: 'http://user:pass@127.0.0.1:7890',
      })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.map((i) => i.path[0])).toContain('proxyUrl')
      }
    })

    it('未选代理类型但填了代理地址 → 校验失败', () => {
      const result = apiDeviceFormSchema.safeParse({
        ...baseApi,
        proxyType: '',
        proxyUrl: 'user:pass@127.0.0.1:7890',
      })
      expect(result.success).toBe(false)
    })

    it('合法代理配置通过校验（user:pass@host:port）', () => {
      const result = apiDeviceFormSchema.safeParse({
        ...baseApi,
        proxyType: 'http',
        proxyUrl: 'user:pass@127.0.0.1:7890',
      })
      expect(result.success).toBe(true)
    })

    it('不配置代理（类型空+地址空）通过校验', () => {
      const result = apiDeviceFormSchema.safeParse({ ...baseApi, proxyType: '', proxyUrl: '' })
      expect(result.success).toBe(true)
    })
  })
})
