/**
 * 设备新增/编辑表单 schema（16_设备域.md §6.2；AGENTS §3.7 RHF+zod）。
 * 随页签三分叉：测试设备/播放设备/测试 API；必填项对照 §6.2 逐字段（标 *）。
 * mock 阶段提交走应用层 mutation；接线后 schema 不变、仅替换 API 桩。
 */
import { z } from 'zod'

/** 测试设备表单（§6.2：名称/型号/设备类型/设备系统/系统版本/应用名称/应用版本/连接方式/序列号必填） */
export const testDeviceFormSchema = z.object({
  name: z.string().min(1, '请填写设备名称'),
  description: z.string().optional(),
  /** 高级设置「备注」（§6.2：与基本信息「描述」拆独立字段，P3-18 返修） */
  remark: z.string().optional(),
  model: z.string().min(1, '请填写型号'),
  deviceType: z.string().min(1, '请选择设备类型'),
  system: z.string().min(1, '请选择设备系统'),
  systemVersion: z.string().min(1, '请填写系统版本'),
  /** API 级别（Android API级别/HarmonyOS API级别，随设备系统切换，§6.2） */
  apiLevel: z.string().optional(),
  appName: z.string().min(1, '请填写应用名称'),
  appVersion: z.string().min(1, '请填写应用版本'),
  connectionType: z.string().min(1, '请选择连接方式'),
  serialNumber: z.string().min(1, '请填写设备序列号'),
  /** 驱动关键字（V9.7.10 添加测试设备 keywords 选填；选项 GET /test-devices/driver-keywords，INT-721 待 INT-725 接线） */
  keywords: z.string().optional(),
  ip: z.string().optional(),
  port: z.string().optional(),
  needsPromptAudio: z.boolean(),
  algorithms: z.array(z.string()),
  tags: z.array(z.string()),
  /** 自定义属性（逗号分隔 key=value，§6.2 高级设置） */
  customAttributes: z.string().optional(),
  priority: z.string(),
})

export type TestDeviceForm = z.infer<typeof testDeviceFormSchema>

/** 播放设备表单（§6.2：名称/型号/设备类型/系统唯一标识/采样率必填；无高级设置分区） */
export const playbackDeviceFormSchema = z.object({
  name: z.string().min(1, '请填写设备名称'),
  description: z.string().optional(),
  model: z.string().min(1, '请填写型号'),
  deviceType: z.string().min(1, '请选择设备类型'),
  deviceUniqueId: z.string().min(1, '请填写系统唯一标识'),
  channelIndex: z.string().optional(),
  /** 支持的通道数（§6.2 INT-381 补口） */
  supportedChannels: z.string().optional(),
  supportedFormats: z.array(z.string()),
  sampleRate: z.string().min(1, '请填写采样率'),
  /** 声压映射 select（§6.2：loadSplMappings，「不使用声压映射」+「{名}(已校准/未校准)」） */
  splMappingId: z.string().optional(),
})

export type PlaybackDeviceForm = z.infer<typeof playbackDeviceFormSchema>

/** 测试 API 表单（§6.2：名称/协议必填；api_endpoints 为主、Master URL 可选兜底——INT-1223/1229） */
export const apiDeviceFormSchema = z
  .object({
    name: z.string().min(1, '请填写 API 名称'),
    description: z.string().optional(),
    vendor: z.string().optional(),
    /** Master 入口 URL（可选；api_endpoints 为主，空值提交侧归一 null 防覆盖既有 api_url） */
    apiUrl: z.string().optional(),
    protocol: z.string().min(1, '请选择协议'),
    environment: z.string().optional(),
    /** 代理类型（INT-1029：http/https/socks5/socks5h，空=不使用代理；api_test_service PROXY_TYPES 契约） */
    proxyType: z.string().optional(),
    /** 代理地址（契约格式 user:pass@host:port，不含 scheme 前缀，INT-846 口径） */
    proxyUrl: z.string().optional(),
    algorithmType: z.string().min(1, '请选择关联算法'),
    maxProcess: z.string().optional(),
    maxTimeout: z.string().optional(),
    maxAudioDuration: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    const type = (data.proxyType ?? '').trim()
    const url = (data.proxyUrl ?? '').trim()
    if (!type && url) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['proxyUrl'],
        message: '未选择代理类型时无需填写代理地址',
      })
      return
    }
    if (type && !url) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['proxyUrl'],
        message: '配置代理时代理地址必填（格式：user:pass@host:port）',
      })
      return
    }
    if (url.includes('://')) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['proxyUrl'],
        message: '代理地址不应包含 http:// 前缀，格式：user:pass@host:port',
      })
    }
  })

export type ApiDeviceForm = z.infer<typeof apiDeviceFormSchema>
