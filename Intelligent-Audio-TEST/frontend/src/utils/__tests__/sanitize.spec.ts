/**
 * sanitize 单元测试 —— HTML 转义/白名单净化（XSS 防护纯函数）
 */
import { describe, it, expect } from 'vitest'
import {
  escapeHtml,
  sanitizeHtml,
  stripHtml,
  sanitizeForVHtml,
  createSafeVHtml,
  sanitizeConclusion,
} from '../sanitize'

describe('escapeHtml', () => {
  it('转义所有危险字符', () => {
    expect(escapeHtml('<script>')).toBe('&lt;script&gt;')
    expect(escapeHtml('a & b')).toBe('a &amp; b')
    expect(escapeHtml('"quote"')).toBe('&quot;quote&quot;')
    expect(escapeHtml("it's")).toBe('it&#x27;s')
    expect(escapeHtml('a/b')).toBe('a&#x2F;b')
    expect(escapeHtml('a=b')).toBe('a&#x3D;b')
    expect(escapeHtml('`x`')).toBe('&#x60;x&#x60;')
  })

  it('空值返回空字符串', () => {
    expect(escapeHtml('')).toBe('')
  })

  it('普通文本原样返回', () => {
    expect(escapeHtml('hello world 123')).toBe('hello world 123')
  })
})

describe('stripHtml', () => {
  it('移除全部标签保留文本', () => {
    expect(stripHtml('<p>hello <b>world</b></p>')).toBe('hello world')
  })

  it('空值返回空字符串', () => {
    expect(stripHtml('')).toBe('')
    expect(stripHtml('no tags')).toBe('no tags')
  })
})

describe('sanitizeHtml', () => {
  it('无白名单时整体转义', () => {
    expect(sanitizeHtml('<b>hi</b>')).toBe(escapeHtml('<b>hi</b>'))
  })

  it('保留白名单标签并移除 on* 事件属性', () => {
    expect(sanitizeHtml('<b onclick="x()">hi</b>', ['b'])).toBe('<b >hi</b>')
  })

  it('移除非白名单标签（保留内部文本）', () => {
    expect(sanitizeHtml('<b>ok</b><script>evil()</script>', ['b'])).toBe('<b>ok</b>evil()')
  })

  it('白名单大小写不敏感', () => {
    expect(sanitizeHtml('<B>up</B>', ['b'])).toBe('<B>up</B>')
  })

  it('移除 javascript: 协议', () => {
    const result = sanitizeHtml('<a href="javascript:alert(1)">x</a>', ['a'])
    expect(result).not.toContain('javascript:')
  })

  it('空值返回空字符串', () => {
    expect(sanitizeHtml('')).toBe('')
  })
})

describe('sanitizeForVHtml / createSafeVHtml / sanitizeConclusion', () => {
  it('保留默认白名单标签', () => {
    expect(sanitizeForVHtml('<b>bold</b><i>it</i>')).toContain('<b>bold</b>')
    expect(sanitizeForVHtml('<b>bold</b><i>it</i>')).toContain('<i>it</i>')
  })

  it('移除 script 标签', () => {
    const result = sanitizeForVHtml('<b>x</b><script>alert(1)</script>')
    expect(result).not.toContain('<script')
    expect(result).not.toContain('</script>')
  })

  it('移除 on* 事件属性', () => {
    const result = sanitizeForVHtml('<div onclick="alert(1)">hi</div>')
    expect(result).not.toContain('onclick')
    expect(result).toContain('hi')
  })

  it('移除危险协议', () => {
    const result = sanitizeForVHtml('<a href="javascript:alert(1)">link</a>')
    expect(result).not.toContain('javascript:')
  })

  it('createSafeVHtml 空值/非字符串安全处理', () => {
    expect(createSafeVHtml(undefined)).toBe('')
    expect(createSafeVHtml(null)).toBe('')
    expect(createSafeVHtml('')).toBe('')
    expect(createSafeVHtml(123 as unknown as string)).toBe('123')
  })

  it('sanitizeConclusion 与 createSafeVHtml 行为一致', () => {
    expect(sanitizeConclusion('<b>t</b>')).toBe(createSafeVHtml('<b>t</b>'))
    expect(sanitizeConclusion(undefined)).toBe('')
  })
})
