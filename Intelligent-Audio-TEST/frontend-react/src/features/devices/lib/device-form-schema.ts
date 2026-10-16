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

/** 测试 API 表单（§6.2：名称/API端点/协议必填；端点列表复用 INT-355 §5.3 口径） */
export const apiDeviceFormSchema = z.object({
  name: z.string().min(1, '请填写 API 名称'),
  description: z.string().optional(),
  vendor: z.string().optional(),
  apiUrl: z.string().min(1, '请填写 API 端点'),
  protocol: z.string().min(1, '请选择协议'),
  environment: z.string().optional(),
  algorithmType: z.string().min(1, '请选择关联算法'),
  maxProcess: z.string().optional(),
  maxTimeout: z.string().optional(),
  maxAudioDuration: z.string().optional(),
})

export type ApiDeviceForm = z.infer<typeof apiDeviceFormSchema>
