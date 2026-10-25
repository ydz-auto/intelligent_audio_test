/**
 * 页签行展开：结果挑选容器的组成四视图（18_挑选合并功能交互重设计.md §5.5.3 ③ / §5.5.4 / §5.5.6，INT-1716）。
 * 替换 `SourceTraceRow` 的**结果挑选分支**（整任务合并分支保持源任务列表，`source` 端点对它不适用）。
 * - 组成区复用落点② 的 `ContainerComposition`（四视图 / 工具行 / 只读树），层级与容器详情、购物车同源；
 * - 保留「来源 {n} 个任务 · 结果 {m} 条」计数行（§5.5.3 ③）；
 * - 首次展开按需补 **1 次** `GET /tasks/{id}`：列表批量已拉过 source，`useCherryPickContainers`
 *   把它预置进 `['task', id, 'cherry-pick-source']`，行展开的 `useContainerComposition` 直接命中；
 * - 首次展开才挂载取数（列表首屏零请求）；之后只隐藏不卸载 → 二次展开 / 切视图全部命中缓存，
 *   视图与筛选的会话态也不丢；展开区高度上限 `max-h-[420px]` 内滚动。
 * - 失效态（§5.5.6）：详情补拉失败（含容器已软删 → 404）→ 「组成加载失败」+ 重试；
 *   `source` 非 200（竞态 / 软删）由 `fetchContainerSourceTrace` 归一 `null` → 「该任务没有合并来源记录」；
 *   `results[].missing` → 叶行「已失效」+ 顶部 Alert（由 `ContainerComposition` 渲染）。
 */
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { useContainerComposition } from '@/application/tasks/use-container-composition'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import type { CherryPickContainer } from '@/domain/models/cherryPick'
import { ContainerComposition } from '@/features/tasks/detail/container-composition'

export function ContainerTraceExpand({
  container,
}: {
  container: CherryPickContainer
}) {
  const [open, setOpen] = useState(false)
  /**
   * 首次展开后才挂载取数体：列表首屏零新增请求（§5.5.3）。
   * 收起时只隐藏不卸载，保证二次展开 / 切视图命中缓存、会话态（视图 / 筛选 / 展开事实）不丢。
   */
  const [everOpened, setEverOpened] = useState(false)

  const toggle = () => {
    setEverOpened(true)
    setOpen((v) => !v)
  }

  return (
    <div className='px-3 py-1'>
      <Button
        variant='ghost'
        size='sm'
        className='text-muted-foreground h-7 gap-1 px-1 text-xs'
        onClick={toggle}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown aria-hidden='true' className='size-3.5' />
        ) : (
          <ChevronRight aria-hidden='true' className='size-3.5' />
        )}
        {open
          ? `收起组成视图（${container.sourceResultCount} 条）`
          : `展开组成视图（${container.sourceResultCount} 条）`}
      </Button>

      {everOpened && (
        <div hidden={!open} className='mt-1'>
          <ContainerTraceExpandBody container={container} />
        </div>
      )}
    </div>
  )
}

function ContainerTraceExpandBody({
  container,
}: {
  container: CherryPickContainer
}) {
  const model = useContainerComposition(container.id)

  // §5.5.6：详情补拉失败（容器已软删 → 404 也走这里）→ Empty + 重试，不白屏
  if (model.detailError) {
    return (
      <Empty className='rounded-xl border border-dashed py-8'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <RefreshCw aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyTitle>组成加载失败</EmptyTitle>
          <EmptyDescription>
            容器详情没能加载出来，来源结果无法用具名信息展示
          </EmptyDescription>
          <EmptyContent>
            <Button variant='outline' size='sm' onClick={model.retry}>
              重试
            </Button>
          </EmptyContent>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className='flex flex-col gap-2'>
      {/* 计数行（§5.5.3 ③ 保留） */}
      <p className='text-muted-foreground font-mono text-xs tabular-nums'>
        来源 {container.sourceTaskCount} 个任务 · 结果 {container.sourceResultCount} 条
      </p>

      {/* 展开区高度上限 420px 内滚动（§5.5.3 ③） */}
      <div className='max-h-[420px] overflow-y-auto pr-1'>
        <ContainerComposition
          trace={model.trace}
          entries={model.entries}
          summary={model.summary}
          loading={model.isLoading || model.detailLoading}
          sectionId={null}
          scrollable={false}
        />
      </div>
    </div>
  )
}
