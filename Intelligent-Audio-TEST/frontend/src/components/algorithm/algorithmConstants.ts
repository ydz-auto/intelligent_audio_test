export const PARAM_CODE_PRESETS: Record<string, {param_name: string; param_type: string; default_value?: string; help_text?: string; min_value?: number; max_value?: number; step?: number; unit?: string}> = {
  'translation_direction': { param_name: '翻译方向', param_type: 'text', help_text: '翻译方向字符串（如 zh2en, en2zh）' },
  'source_language': { param_name: '源语种', param_type: 'text', help_text: '源语言代码（如 zh, en, ja）' },
  'target_language': { param_name: '目标语种', param_type: 'text', help_text: '目标语言代码（如 en, ja, zh）' },
  'overlap_rate': { param_name: '交叠率', param_type: 'slider', default_value: '0', help_text: '音频交叠比例(0~1)', min_value: 0, max_value: 1, step: 0.05 },
  'overlap_time': { param_name: '交叠时间(秒)', param_type: 'number', default_value: '0', help_text: '音频交叠时间（秒），优先级高于交叠率', min_value: 0, max_value: 30, step: 0.5, unit: 's' },
  'railDistance': { param_name: '导轨距离(cm)', param_type: 'slider', help_text: '导轨距离，本轮结束后自动复位', min_value: 10, max_value: 200, step: 5, unit: 'cm' },
  'volumeLevel': { param_name: '被测设备音量', param_type: 'slider', help_text: '被测设备音量(0-100)', min_value: 0, max_value: 100, step: 1 },
  'voiceprintEnabled': { param_name: '声纹注册', param_type: 'switch', default_value: 'false', help_text: '是否在本轮播放声纹注册音频' },
  'voiceprintAudioId': { param_name: '声纹注册音频', param_type: 'audio_select', help_text: '声纹注册音频文件' },
  'voiceprintPlaybackDeviceId': { param_name: '声纹播放设备', param_type: 'device_select', help_text: '声纹注册音频播放设备' },
  'voiceprintSpl': { param_name: '声纹播放声压级', param_type: 'number', default_value: '70.0', help_text: '声纹注册音频播放声压级', min_value: 20, max_value: 100, step: 1, unit: 'dB' },
  'voiceprintWaitTime': { param_name: '声纹等待时间(秒)', param_type: 'number', default_value: '5.0', help_text: '声纹注册后等待时间', min_value: 0, max_value: 60, step: 1, unit: 's' },
  'interferers': { param_name: '干扰人列表', param_type: 'json', default_value: '[]', help_text: '干扰人配置列表' },
  'promptAudioId': { param_name: 'Prompt 音频', param_type: 'audio_select', help_text: '在干声播放之前播放的引导音频' },
  'inputText': { param_name: '输入文本', param_type: 'text', help_text: '发送给 API 的文本内容' },
  'inputAudio': { param_name: '输入音频', param_type: 'audio_select', help_text: '发送给 API 的音频文件' },
  'asr_ref': { param_name: 'ASR参考文本', param_type: 'text', help_text: 'ASR识别参考文本' },
  'tran_ref': { param_name: '翻译参考文本', param_type: 'text', help_text: '翻译参考文本' },
}

// 功能特性快捷开关：每个 bundle 对应一组 param_code
export const FEATURE_BUNDLES: Record<string, { label: string; scope: string; params: string[] }> = {
  translation: { label: '翻译方向', scope: 'common', params: ['translation_direction', 'source_language', 'target_language'] },
  voiceprint: { label: '声纹注册', scope: 'e2e', params: ['voiceprintEnabled', 'voiceprintAudioId', 'voiceprintPlaybackDeviceId', 'voiceprintSpl', 'voiceprintWaitTime'] },
  interferer: { label: '干扰人', scope: 'e2e', params: ['interferers'] },
  env_device: { label: '环境设备', scope: 'e2e', params: ['railDistance', 'volumeLevel'] },
  overlap: { label: '交叠播放', scope: 'e2e', params: ['overlap_rate', 'overlap_time'] },
  prompt_audio: { label: 'Prompt音频', scope: 'common', params: ['promptAudioId'] },
}

export const NEW_GROUP_SENTINEL = '__new_group__'
