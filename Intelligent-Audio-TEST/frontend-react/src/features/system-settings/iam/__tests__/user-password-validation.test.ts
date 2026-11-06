/**
 * 用户抽屉密码校验单测（INT-1584）。
 * 用户管理入口口径 8–128 位：新建必填、编辑留空不改；纯空白按空处理，
 * 内部空格保留。校验不通过时调用方零请求，这里只测判定本身。
 */
import { describe, expect, it } from 'vitest'

import { validateUserPassword } from '@/features/system-settings/iam/password-validation'

describe('validateUserPassword', () => {
  it('新建态：空值与纯空白都提示必填', () => {
    expect(validateUserPassword('', 'create')).toBe('请输入密码')
    expect(validateUserPassword('   ', 'create')).toBe('请输入密码')
  })

  it('新建态：1/7/129 位非法，8 与 128 位合法', () => {
    expect(validateUserPassword('x', 'create')).toBe('密码长度需为 8–128 位')
    expect(validateUserPassword('x'.repeat(7), 'create')).toBe(
      '密码长度需为 8–128 位'
    )
    expect(validateUserPassword('x'.repeat(129), 'create')).toBe(
      '密码长度需为 8–128 位'
    )
    expect(validateUserPassword('x'.repeat(8), 'create')).toBe('')
    expect(validateUserPassword('x'.repeat(128), 'create')).toBe('')
  })

  it('编辑态：留空表示不修改，不报错', () => {
    expect(validateUserPassword('', 'edit')).toBe('')
    expect(validateUserPassword('  ', 'edit')).toBe('')
  })

  it('编辑态：一旦填写即按 8–128 位校验', () => {
    expect(validateUserPassword('x'.repeat(7), 'edit')).toBe(
      '密码长度需为 8–128 位'
    )
    expect(validateUserPassword('x'.repeat(129), 'edit')).toBe(
      '密码长度需为 8–128 位'
    )
    expect(validateUserPassword('x'.repeat(8), 'edit')).toBe('')
  })

  it('首尾空白先 trim 再计长度，内部空格保留', () => {
    expect(validateUserPassword('  abcdef  ', 'create')).toBe(
      '密码长度需为 8–128 位'
    )
    expect(validateUserPassword(' ab cd ef ', 'create')).toBe('')
  })
})
