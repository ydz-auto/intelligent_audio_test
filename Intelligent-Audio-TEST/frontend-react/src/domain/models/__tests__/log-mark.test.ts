/**
 * 行内标记开关语义（domain 层；INT-1947）。
 * 基线 = V9.7.10 `LogViewLogic/logView.ts:418-428`：`newMark = log.mark === 颜色 ? '' : 颜色`。
 * 空串必须原样透传（`PUT /logs/mark {mark:''}` 是后端清空口径），不能被默认值顶成 'flagged'。
 */
import { describe, expect, it } from 'vitest'

import { nextLogMark } from '@/domain/models/log'

describe('nextLogMark', () => {
  it('未标记行点色 → 打上该色', () => {
    expect(nextLogMark(null, 'yellow')).toBe('yellow')
    expect(nextLogMark(undefined, 'red')).toBe('red')
    expect(nextLogMark('', 'blue')).toBe('blue')
  })

  it('点已有同色 → 清除（空串）', () => {
    expect(nextLogMark('yellow', 'yellow')).toBe('')
    expect(nextLogMark('red', 'red')).toBe('')
  })

  it('换色 → 覆盖为新色，不误清', () => {
    expect(nextLogMark('yellow', 'green')).toBe('green')
    expect(nextLogMark('blue', 'yellow')).toBe('yellow')
  })
})
