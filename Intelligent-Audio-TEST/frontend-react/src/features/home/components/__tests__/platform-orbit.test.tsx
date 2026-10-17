/**
 * 首页枢纽图算法能力 floating 芯片（INT-635 重新设计，03_首页.md §3.2）：
 * 六枚芯片 = 圆形玻璃徽章（rounded-full 中性卡面 + 图标色 + 同源辉光阴影）
 * + 悬浮文字标签；旗舰「实时语音大模型」带 ring-2 ring-primary/40 强调；
 * 小屏（<lg）对角两枚（声纹/通话）仍带 `hidden` 类防遮挡。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PlatformOrbit } from '@/features/home/components/platform-orbit'
import { ORBIT_ALGORITHM_NODES } from '@/features/home/constants'

function renderOrbit() {
  return render(<PlatformOrbit />)
}

describe('PlatformOrbit 算法能力 floating 芯片（INT-635）', () => {
  it('六枚芯片名称齐全，徽章 + 悬浮文字标签 DOM 形态正确', () => {
    const { container } = renderOrbit()
    const orbit = container.querySelector("[aria-label='平台总览']")
    expect(orbit).not.toBeNull()

    // 六枚名称逐字渲染
    for (const node of ORBIT_ALGORITHM_NODES) {
      expect(screen.getByText(node.name)).toBeInTheDocument()
    }

    // 徽章 = span.rounded-full（圆形），仅六枚（四角节点卡/中心卡非 rounded-full span）
    const medallions = orbit!.querySelectorAll('span.rounded-full')
    expect(medallions).toHaveLength(6)

    // 卡面中性：徽章面 bg-card/90（无彩色底），图标色与辉光由 color/glow 承担
    medallions.forEach((el) => {
      expect(el.className).toContain('bg-card/90')
      expect(el.className).toContain('border-border/70')
      expect(el.className).toContain('shadow-md')
    })

    // 每枚徽章内均有 lucide 图标（svg）
    expect(orbit!.querySelectorAll('span.rounded-full svg')).toHaveLength(6)

    // 悬浮文字标签 = span.text-center.text-muted-foreground（无描边盒），六枚
    // （通话芯片徽章的图标色同为 text-muted-foreground，用 text-center 区分徽章/标签）
    const labels = orbit!.querySelectorAll(
      'span.text-center.text-muted-foreground'
    )
    expect(labels).toHaveLength(6)
  })

  it('旗舰「实时语音大模型」仅一枚带 ring-2 ring-primary/40 强调光晕', () => {
    const { container } = renderOrbit()
    const orbit = container.querySelector("[aria-label='平台总览']")
    const flagship = orbit!.querySelector('span.rounded-full.ring-2')
    expect(flagship).not.toBeNull()
    expect(flagship!.className).toContain('ring-primary/40')
    expect(orbit!.querySelectorAll('span.rounded-full.ring-2')).toHaveLength(1)
  })

  it('小屏断点对角两枚芯片（声纹/通话）带 hidden 类防遮挡', () => {
    renderOrbit()
    const hiddenNodes = ORBIT_ALGORITHM_NODES.filter(
      (n) => n.name.includes('声纹') || n.name.includes('通话')
    )
    expect(hiddenNodes).toHaveLength(2)
    for (const node of hiddenNodes) {
      const wrapper = screen.getByText(node.name).parentElement
      expect(wrapper!.className).toContain('hidden')
      expect(wrapper!.className).toContain('lg:flex')
    }
    // 其余四枚小屏可见（无 hidden 类）
    for (const node of ORBIT_ALGORITHM_NODES.filter(
      (n) => !hiddenNodes.includes(n)
    )) {
      const wrapper = screen.getByText(node.name).parentElement
      expect(wrapper!.className).not.toContain('hidden')
    }
  })
})
