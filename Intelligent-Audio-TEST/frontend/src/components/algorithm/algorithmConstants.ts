import { TestType } from '@/domain/enums'

export const PARAM_CODE_PRESETS: Record<string, {paramName: string; paramType: string; defaultValue?: string; helpText?: string; minValue?: number; maxValue?: number; step?: number; unit?: string}> = {
  'translation_direction': { paramName: '翻译方向', paramType: 'text', helpText: '翻译方向字符串（如 zh2en, en2zh）' },
  'source_language': { paramName: '源语种', paramType: 'text', helpText: '源语言代码（如 zh, en, ja）' },
  'target_language': { paramName: '目标语种', paramType: 'text', helpText: '目标语言代码（如 en, ja, zh）' },
  'overlap_rate': { paramName: '交叠率', paramType: 'slider', defaultValue: '0', helpText: '音频交叠比例(0~1)', minValue: 0, maxValue: 1, step: 0.05 },
  'overlap_time': { paramName: '交叠时间(秒)', paramType: 'number', defaultValue: '0', helpText: '音频交叠时间（秒），优先级高于交叠率', minValue: 0, maxValue: 30, step: 0.5, unit: 's' },
  'railDistance': { paramName: '导轨距离(cm)', paramType: 'slider', helpText: '导轨距离，本轮结束后自动复位', minValue: 10, maxValue: 200, step: 5, unit: 'cm' },
  'volumeLevel': { paramName: '被测设备音量', paramType: 'slider', helpText: '被测设备音量(0-100)', minValue: 0, maxValue: 100, step: 1 },
  'voiceprint': { paramName: '声纹注册', paramType: 'audio_select', helpText: '声纹注册音频配置（含音频、设备、声压级、等待时间）' },
  'interferers': { paramName: '干扰人列表', paramType: 'audio_select', defaultValue: '[]', helpText: '干扰人配置列表（每个含音频、设备、声压级）' },
  'promptAudioId': { paramName: 'Prompt 音频', paramType: 'audio_select', helpText: '在干声播放之前播放的引导音频' },
  'inputText': { paramName: '输入文本', paramType: 'text', helpText: '发送给 API 的文本内容' },
  'inputAudio': { paramName: '输入音频', paramType: 'audio_select', helpText: '发送给 API 的音频文件' },
  'asr_ref': { paramName: 'ASR参考文本', paramType: 'text', helpText: 'ASR识别参考文本' },
  'tran_ref': { paramName: '翻译参考文本', paramType: 'text', helpText: '翻译参考文本' },
}

// 功能特性快捷开关：每个 bundle 对应一组 param_code
export const FEATURE_BUNDLES: Record<string, { label: string; scope: string; params: string[] }> = {
  translation: { label: '翻译方向', scope: 'common', params: ['translation_direction', 'source_language', 'target_language'] },
  voiceprint: { label: '声纹注册', scope: TestType.E2E, params: ['voiceprint'] },
  interferer: { label: '干扰人', scope: TestType.E2E, params: ['interferers'] },
  env_device: { label: '环境设备', scope: TestType.E2E, params: ['railDistance', 'volumeLevel'] },
  overlap: { label: '交叠播放', scope: TestType.E2E, params: ['overlap_rate', 'overlap_time'] },
  prompt_audio: { label: 'Prompt音频', scope: 'common', params: ['promptAudioId'] },
}

export const NEW_GROUP_SENTINEL = '__new_group__'
