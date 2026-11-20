/**
 * 图表视口懒加载壳：容器进入视口（含 `#task-charts` 锚点直达）才拉取 VChart 分块并渲染。
 * 视口外只渲染一个空占位 div —— 工作台首屏不再随路由下载约 2MB 的图表分块。
 */
import { lazy, Suspense, useEffect, useRef, useState } from 'react'

import { Skeleton } from '@/components/ui/skeleton'

import type { DashboardChartProps } from './chart-canvas'

const DashboardChart = lazy(() =>
  import('./chart-canvas').then((module) => ({
    default: module.DashboardChart,
  }))
)

export function LazyChartCanvas(props: DashboardChartProps) {
  const holderRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const holder = holderRef.current
    if (!holder || visible) return
    // 环境不支持 IntersectionObserver（老浏览器 / 测试桩缺失）时直接渲染，不阻塞图表
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(holder)
    return () => observer.disconnect()
  }, [visible])

  return (
    <div ref={holderRef} className='h-full w-full'>
      {visible && (
        <Suspense fallback={<Skeleton className='h-full w-full' />}>
          <DashboardChart {...props} />
        </Suspense>
      )}
    </div>
  )
}
