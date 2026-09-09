export const ANNOTATION_TYPES = [
  { value: 'asr', label: 'asr' },
  { value: 'translation', label: 'translation' },
  { value: 'reference', label: 'reference' },
  { value: 'diarization', label: 'diarization' },
  { value: 'voice_llm', label: 'voice_llm' }
]

/** 内置标注代码集合（用于判断是否走自定义输入框） */
export const BUILTIN_ANNOTATION_CODES = ANNOTATION_TYPES.map((item) => item.value)

export const ANNOTATION_FORMATS = [
  { value: 'text', label: '文本' },
  { value: 'json', label: 'JSON' },
  { value: 'rttm', label: 'RTTM' },
  { value: 'stm', label: 'STM' }
]

export const REFERENCE_PARAM_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'audio', label: '音频' },
  { value: 'json', label: 'JSON' },
  { value: 'rttm', label: 'RTTM' },
  { value: 'stm', label: 'STM' }
]
