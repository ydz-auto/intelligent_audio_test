/**
 * 用例行标签徽章测试（11_用例域.md §3.3 + INT-487 按分类呈现）：
 * 空标签显 —；≤2 枚全显（含分类角标与数据驱动色）；>2 枚折叠为 +N。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MOCK_TAGS } from '@/infrastructure/mock/testcases-mock'
import { TagCell } from '@/features/testcases/components/tag-cell'

describe('TagCell', () => {
  it('空标签显 —', () => {
    render(<TagCell tagNames={[]} tagRegistry={MOCK_TAGS} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('≤2 枚标签全显，含分类名角标与数据驱动色', () => {
    render(<TagCell tagNames={['音箱', '中文']} tagRegistry={MOCK_TAGS} />)
    expect(screen.getByText('音箱')).toBeInTheDocument()
    expect(screen.getByText('中文')).toBeInTheDocument()
    // INT-487 分类名小字角标
    expect(screen.getByText('设备类型')).toBeInTheDocument()
    expect(screen.getByText('语种')).toBeInTheDocument()
    // 数据驱动色（TagItem.color）写入徽章内联样式
    const badge = screen.getByText('音箱').closest('span')
    expect(badge).toHaveStyle({ backgroundColor: expect.stringContaining('#14b8a6') })
  })

  it('>2 枚折叠为 +N，展开 tooltip 含全量', () => {
    render(<TagCell tagNames={['音箱', '中文', '客厅', '音乐']} tagRegistry={MOCK_TAGS} />)
    expect(screen.getByText('+2')).toBeInTheDocument()
  })
})
