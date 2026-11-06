/**
 * lib/utils 纯函数测试（照 newAPI 纯函数测试粒度）。
 */
import { describe, expect, it } from 'vitest'

import {
  getPageNumbers,
  sanitizeCssVariableName,
  truncateText,
  tryPrettyJson,
} from '@/lib/utils'

describe('getPageNumbers', () => {
  it('按顺序列出不超过 4 页的全部分页号', () => {
    expect(getPageNumbers(1, 4)).toEqual([1, 2, 3, 4])
    expect(getPageNumbers(3, 1)).toEqual([1])
  })

  it('靠近开头时省略尾部（1, 2, …, total）', () => {
    expect(getPageNumbers(1, 10)).toEqual([1, 2, '...', 10])
    expect(getPageNumbers(2, 10)).toEqual([1, 2, '...', 10])
  })

  it('靠近末尾时省略前部（1, …, total-1, total）', () => {
    expect(getPageNumbers(9, 10)).toEqual([1, '...', 9, 10])
    expect(getPageNumbers(10, 10)).toEqual([1, '...', 9, 10])
  })

  it('中段用省略号包裹当前页（1, …, cur, …, total）', () => {
    expect(getPageNumbers(5, 10)).toEqual([1, '...', 5, '...', 10])
  })
})

describe('sanitizeCssVariableName', () => {
  it('把点号/空格/斜杠替换为连字符', () => {
    expect(sanitizeCssVariableName('gpt-3.5-turbo')).toBe('gpt-3-5-turbo')
    expect(sanitizeCssVariableName('asr streaming/v2')).toBe(
      'asr-streaming-v2'
    )
  })

  it('移除其余非单词字符', () => {
    expect(sanitizeCssVariableName('a@b(c)')).toBe('abc')
  })
})

describe('truncateText', () => {
  it('超过上限时截断并补省略号', () => {
    expect(truncateText('智能语音测试平台', 4)).toBe('智能语音...')
  })

  it('未超上限原样返回，空串返回空串', () => {
    expect(truncateText('abc', 5)).toBe('abc')
    expect(truncateText('', 5)).toBe('')
  })
})

describe('tryPrettyJson', () => {
  it('合法 JSON 美化为两空格缩进', () => {
    expect(tryPrettyJson('{"a":1}')).toBe('{\n  "a": 1\n}')
  })

  it('非法 JSON 原样返回，空串返回空串', () => {
    expect(tryPrettyJson('not-json')).toBe('not-json')
    expect(tryPrettyJson('  ')).toBe('')
  })
})
