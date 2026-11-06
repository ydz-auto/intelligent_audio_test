/**
 * 数学定界符判定（INT-1274）：口径必须与 markdown.tsx 的自定义 tokenizer 一致，
 * 漏判会让公式退化成纯文本，多判只多下载一次 katex。
 */
import { describe, expect, it } from 'vitest'

import { hasMathSyntax } from '@/lib/katex-loader'

describe('hasMathSyntax', () => {
  it('识别块级 $$ 行与行内 $$…$$', () => {
    expect(hasMathSyntax('$$\nE = mc^2\n$$')).toBe(true)
    expect(hasMathSyntax('质能方程 $$E = mc^2$$ 就是这样')).toBe(true)
  })

  it('识别 ```math / ```katex / ```latex 围栏', () => {
    expect(hasMathSyntax('```math\nx^2\n```')).toBe(true)
    expect(hasMathSyntax('```katex\nx^2\n```')).toBe(true)
    expect(hasMathSyntax('```latex\nx^2\n```')).toBe(true)
  })

  it('识别 \\(…\\) 与 \\[…\\] 写法', () => {
    expect(hasMathSyntax('行内 \\(a+b\\) 公式')).toBe(true)
    expect(hasMathSyntax('显示 \\[a+b\\] 公式')).toBe(true)
  })

  it('普通正文与普通代码围栏不算公式', () => {
    expect(hasMathSyntax('# 平台使用手册')).toBe(false)
    expect(hasMathSyntax('价格是 100 元，没有美元符号')).toBe(false)
    expect(hasMathSyntax('```bash\nls -l\n```')).toBe(false)
  })
})
