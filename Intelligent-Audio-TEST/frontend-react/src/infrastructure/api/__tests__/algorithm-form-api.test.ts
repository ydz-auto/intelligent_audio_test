/**
 * 算法参数表单 schema 字段展平去重单测（INT-1686 P3）：
 * 后端部分算法 schema 同时下发顶层 fields 与 groups[].fields，两处都含同一字段，
 * 直接拼接会让同一字段渲染两个输入框——dedupeFormFields 按 fieldCode 只保留首次出现。
 */
import { describe, expect, it } from 'vitest'

import {
  dedupeFormFields,
  type AlgorithmFormField,
} from '@/infrastructure/api/algorithm-form-api'

const field = (code: string, label = code): AlgorithmFormField => ({
  code,
  label,
  component: 'input',
  type: 'text',
  required: false,
  defaultValue: undefined,
  helpText: null,
  hidden: false,
  scope: null,
})

describe('dedupeFormFields（INT-1686 P3）', () => {
  it('顶层与分组内同 fieldCode 只保留首次出现的一个', () => {
    const out = dedupeFormFields([
      field('threshold', '接线测试阈值'),
      field('other', '其他字段'),
      field('threshold', '接线测试阈值'),
    ])
    expect(out.map((f) => f.code)).toEqual(['threshold', 'other'])
    expect(out).toHaveLength(2)
  })

  it('无重复时原样保序', () => {
    const out = dedupeFormFields([field('a'), field('b'), field('c')])
    expect(out.map((f) => f.code)).toEqual(['a', 'b', 'c'])
  })

  it('fieldCode 为空的行无法判定同源，原样保留', () => {
    const out = dedupeFormFields([field(''), field(''), field('a')])
    expect(out).toHaveLength(3)
  })

  it('空输入返回空数组', () => {
    expect(dedupeFormFields([])).toEqual([])
  })
})
