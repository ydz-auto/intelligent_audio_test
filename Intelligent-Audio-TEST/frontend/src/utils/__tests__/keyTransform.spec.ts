/**
 * keyTransform 单元测试 —— snake_case ⇄ camelCase 键名深度转换
 * 验证 domain(D4) 规则：infrastructure 层负责字段名适配，值（枚举/路径）原样保留
 */
import { describe, it, expect } from 'vitest'
import { snakeToCamel, readCamel, camelizeKeys, snakifyKeys } from '../keyTransform'

describe('snakeToCamel', () => {
  it('转换单个 snake_case key', () => {
    expect(snakeToCamel('audio_type')).toBe('audioType')
    expect(snakeToCamel('file_path')).toBe('filePath')
  })

  it('多个下划线段', () => {
    expect(snakeToCamel('audio_file_path')).toBe('audioFilePath')
    expect(snakeToCamel('a_b_c')).toBe('aBC')
  })

  it('无下划线时原样返回', () => {
    expect(snakeToCamel('alreadyCamel')).toBe('alreadyCamel')
    expect(snakeToCamel('id')).toBe('id')
  })

  it('不改变大写字母后的下划线（只匹配 _小写）', () => {
    expect(snakeToCamel('a_B')).toBe('a_B')
  })
})

describe('readCamel', () => {
  it('优先读取 camelCase key', () => {
    expect(readCamel({ audioType: 'dry' }, 'audioType')).toBe('dry')
  })

  it('camelCase 缺失时兜底 snake_case key', () => {
    expect(readCamel({ audio_type: 'noise' }, 'audioType')).toBe('noise')
  })

  it('两个 key 同时存在时取 camelCase', () => {
    expect(readCamel({ audioType: 'dry', audio_type: 'noise' }, 'audioType')).toBe('dry')
  })

  it('都不存在时返回 undefined', () => {
    expect(readCamel({}, 'audioType')).toBeUndefined()
  })

  it('非对象输入返回 undefined', () => {
    expect(readCamel(null, 'audioType')).toBeUndefined()
    expect(readCamel(undefined, 'audioType')).toBeUndefined()
    expect(readCamel('str', 'audioType')).toBeUndefined()
  })
})

describe('camelizeKeys', () => {
  it('递归转换嵌套对象', () => {
    const input = {
      audio_type: 'dry',
      file_info: { file_path: '/a/b.wav', sample_rate: 44100 },
    }
    expect(camelizeKeys(input)).toEqual({
      audioType: 'dry',
      fileInfo: { filePath: '/a/b.wav', sampleRate: 44100 },
    })
  })

  it('递归转换数组内对象', () => {
    const input = [{ created_at: '2024-01-01' }, { updated_at: '2024-01-02' }]
    expect(camelizeKeys(input)).toEqual([{ createdAt: '2024-01-01' }, { updatedAt: '2024-01-02' }])
  })

  it('只转 key 不碰 value', () => {
    // 值中的下划线（枚举值/路径/文件名）必须原样保留
    const input = { file_name: 'my_file.txt', audio_type: 'audio_file' }
    expect(camelizeKeys(input)).toEqual({ fileName: 'my_file.txt', audioType: 'audio_file' })
  })

  it('原始类型与 null 原样返回', () => {
    expect(camelizeKeys(42)).toBe(42)
    expect(camelizeKeys('str')).toBe('str')
    expect(camelizeKeys(null)).toBeNull()
  })
})

describe('snakifyKeys', () => {
  it('递归转换嵌套对象与数组', () => {
    const input = { taskCase: { caseIds: [1, 2], items: [{ groupId: 3 }] } }
    expect(snakifyKeys(input)).toEqual({
      task_case: { case_ids: [1, 2], items: [{ group_id: 3 }] },
    })
  })

  it('与 camelizeKeys 互逆（roundtrip）', () => {
    const original = {
      audio_type: 'dry',
      file_info: { file_path: '/a/b.wav', tags: ['x_y'] },
      items: [{ created_at: 't' }],
    }
    expect(snakifyKeys(camelizeKeys(original))).toEqual(original)
  })

  it('原始类型与 null 原样返回', () => {
    expect(snakifyKeys(7)).toBe(7)
    expect(snakifyKeys(null)).toBeNull()
  })
})
