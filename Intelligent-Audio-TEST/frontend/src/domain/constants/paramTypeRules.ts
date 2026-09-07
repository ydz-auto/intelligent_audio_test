import { FieldType, type FieldTypeType } from '@/domain/enums'

/**
 * 参数类型推断规则配置：按顺序匹配「关键词 → FieldType」。
 * 与后端 report_service/application/services/report_helpers.py 的
 * _PARAM_TYPE_KEYWORD_RULES 保持一致；注：'timestamp' 含 'time'，仅需匹配 'time'。
 */
export const PARAM_TYPE_KEYWORD_RULES: ReadonlyArray<{
  keyword: string
  type: FieldTypeType
}> = [
  { keyword: 'rttm', type: FieldType.RTTM },
  { keyword: 'stm', type: FieldType.STM },
  { keyword: 'audio', type: FieldType.AUDIO },
  { keyword: 'time', type: FieldType.TIMESTAMP },
]

/** 根据参数键名推断字段类型（领域纯函数，替代散落在组件内的魔法字符串判断） */
export function inferParamType(paramKey: string): FieldTypeType {
  const lower = paramKey.toLowerCase()
  for (const rule of PARAM_TYPE_KEYWORD_RULES) {
    if (lower.includes(rule.keyword)) {
      return rule.type
    }
  }
  return FieldType.TEXT
}

/** 时间轴相关字段类型集合（RTTM/STM/JSON），供报告时间轴过滤复用。
 * 比较目标为 DTO 的任意字符串 paramType，故元素类型放宽为 string（值仍取自 FieldType） */
export const TIMELINE_PARAM_TYPES: ReadonlyArray<string> = [
  FieldType.RTTM,
  FieldType.STM,
  FieldType.JSON,
]
