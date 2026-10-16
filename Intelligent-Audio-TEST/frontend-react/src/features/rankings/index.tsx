/**
 * 排行榜页（14_benchmark排行.md §4.1，/rankings 公开路由页面本体）：
 * 背景光晕 + PageTransition 容器 + Hero + 算法卡片网格 + 筛选行 + 指标组卡 ×N。
 * 三态路由：首访加载骨架 / 权限空态（403，不跳登录——INT-344 口径）/
 * 错误态 / 空态 / 数据态。
 */
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Lock, RefreshCw, Trophy } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import {
  DEFAULT_RANKING_SEARCH,
  searchToFilters,
  type RankingSearch,
} from '@/application/rankings/rankingFilters'
import { useBenchmarkAccess } from '@/application/rankings/useBenchmarkAccess'
import { useComputeRanking } from '@/application/rankings/useComputeRanking'
import { useRankings } from '@/application/rankings/useRankings'
import { PageTransition } from '@/components/page-transition'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { PublicFooter, PublicHeader } from '@/features/home/components/public-shell'
import { useRankingAlgorithmStore } from '@/infrastructure/stores/ranking-algorithm-store'

import { RankingAlgorithmCardGrid } from './components/algorithm-card-grid'
import { MetricGroupCard } from './components/metric-group-card'
import { RankingFiltersBar } from './components/ranking-filters'
import { RankingsHero } from './components/rankings-hero'
import { useRankingView } from './lib/use-ranking-view'

export function RankingsPage() {
  const navigate = useNavigate()
  const rawSearch = useSearch({ strict: false }) as unknown as RankingSearch
  const search: RankingSearch = { ...DEFAULT_RANKING_SEARCH, ...rawSearch }
  const filters = searchToFilters(search)
  const { canRead, canCompute } = useBenchmarkAccess()
  const ranking = useRankings(filters, canRead)
  const { view, setView } = useRankingView()

  // 重算链路（页面层统一持有：筛选行「立即计算」与空态「立即计算」共用同一
  // ConfirmDialog + mutation——§5.2；空态不再是清空筛选的假导航）
  const compute = useComputeRanking()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const handleCompute = useCallback(() => {
    compute.mutate(
      {
        suite: filters.suite || undefined,
        category: filters.category || undefined,
        source: filters.source || undefined,
      },
      { onSettled: () => setConfirmOpen(false) }
    )
  }, [compute, filters])

  // URL `algorithm=` 可还原 → 页内 store（页内独立，不写回全局）
  const setAlgorithm = useRankingAlgorithmStore((s) => s.setAlgorithm)
  const algorithmType = useRankingAlgorithmStore((s) => s.algorithmType)
  useEffect(() => {
    if (search.algorithm) setAlgorithm(search.algorithm)
  }, [search.algorithm, setAlgorithm])

  // 页内算法切换 → 写回 URL search（algorithm= 可分享/刷新还原）
  useEffect(() => {
    const current = algorithmType ?? ''
    if ((search.algorithm ?? '') !== current) {
      void navigate({
        to: '/rankings',
        search: (prev) => ({ ...prev, algorithm: current }),
      })
    }
  }, [algorithmType, search.algorithm, navigate])

  const handleFilterChange = (patch: Partial<typeof filters>) => {
    void navigate({
      to: '/rankings',
      search: (prev) => ({ ...prev, ...patch }),
    })
  }

  const handleReset = () => {
    void navigate({
      to: '/rankings',
      search: (prev) => ({
        ...prev,
        category: '',
        suite: '',
        metricCode: '',
        source: '',
        subjectName: '',
      }),
    })
  }

  return (
    <div className='bg-background min-h-svh'>
      <PublicHeader />
      <div className='relative'>
        {/* 背景光晕层（163° 主绿 / 200° 青蓝 / 280° 点缀；底部渐隐，照 newAPI index.tsx:95-108） */}
        <div
          aria-hidden='true'
          className='absolute inset-x-0 top-0 h-[600px] opacity-20 dark:opacity-[0.10]'
          style={{
            backgroundImage:
              'radial-gradient(ellipse at 20% 50%, hsl(163 70% 50%), transparent 60%), radial-gradient(ellipse at 40% 20%, hsl(200 80% 60%), transparent 55%), radial-gradient(ellipse at 60% 40%, hsl(280 60% 60%), transparent 60%)',
            maskImage:
              'linear-gradient(to bottom, black 40%, transparent 100%)',
            WebkitMaskImage:
              'linear-gradient(to bottom, black 40%, transparent 100%)',
          }}
        />
        <PageTransition className='relative mx-auto w-full max-w-[1280px] space-y-8 px-3 pt-16 pb-10 sm:px-6 sm:pt-20 sm:pb-12 xl:px-8'>
          <RankingsHero category={filters.category} />
          {/* 算法卡片网格（§4.5：Hero 之下、筛选行之上的算法选择区，页内独立） */}
          <RankingAlgorithmCardGrid />

          {!canRead ? (
            <PermissionEmpty />
          ) : ranking.isLoading ? (
            <LoadingSkeleton />
          ) : ranking.isError ? (
            <ErrorState
              message={ranking.errorMessage ?? '查询排行失败，请稍后重试'}
              onRetry={() =>
                void navigate({
                  to: '/rankings',
                  search: (prev) => ({ ...prev }),
                })
              }
            />
          ) : ranking.groups.length === 0 ? (
            <EmptyState
              canCompute={canCompute}
              onCompute={() => setConfirmOpen(true)}
            />
          ) : (
            <>
              <RankingFiltersBar
                filters={filters}
                suites={ranking.suites}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                isFetching={ranking.isFetching}
                onCompute={() => setConfirmOpen(true)}
                computePending={compute.isPending}
              />
              {ranking.groups.map((group) => (
                <MetricGroupCard
                  key={`${group.metricCode}-${group.scenarioKey}`}
                  group={group}
                  view={view}
                  onViewChange={setView}
                />
              ))}
            </>
          )}

          {/* 重算确认弹窗（§5.2：筛选行与空态共用；计算是同步接口不做轮询） */}
          <ConfirmDialog
            open={confirmOpen}
            onOpenChange={setConfirmOpen}
            title='重新计算排行？'
            desc='将合并平台实测与外部基线全量重算，期间现有排行保持可查看。'
            confirmText='开始计算'
            handleConfirm={handleCompute}
            isLoading={compute.isPending}
          />
        </PageTransition>
      </div>
      <PublicFooter />
    </div>
  )
}

/** 首访加载骨架（§5.1：Hero 骨架条 + 算法网格骨架 + 筛选行骨架 + 组卡骨架×2） */
function LoadingSkeleton() {
  return (
    <>
      <div className='flex flex-col gap-2'>
        <Skeleton className='h-10 w-48 rounded-md' />
        <Skeleton className='h-4 w-full max-w-xl rounded-md' />
        <Skeleton className='mt-2 h-9 w-full max-w-2xl rounded-md' />
      </div>
      <div className='grid gap-3 sm:grid-cols-2 xl:grid-cols-3'>
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className='h-32 rounded-xl' />
        ))}
      </div>
      <div className='flex flex-wrap gap-2'>
        <Skeleton className='h-8 w-40 rounded-lg' />
        <Skeleton className='h-8 w-40 rounded-lg' />
        <Skeleton className='h-8 w-32 rounded-lg' />
        <Skeleton className='h-8 w-52 rounded-lg' />
      </div>
      <div className='space-y-8'>
        <GroupCardSkeleton />
        <GroupCardSkeleton />
      </div>
    </>
  )
}

function GroupCardSkeleton() {
  return (
    <div className='bg-card ring-foreground/10 overflow-hidden rounded-xl border ring-1'>
      <div className='flex items-start justify-between gap-4 px-5 py-4'>
        <div className='flex flex-col gap-1.5'>
          <Skeleton className='h-5 w-40 rounded-md' />
          <Skeleton className='h-4 w-72 rounded-md' />
        </div>
        <Skeleton className='h-9 w-12 rounded-md' />
      </div>
      <div className='px-5 pb-5'>
        <Skeleton className='h-60 w-full rounded-lg sm:h-72' />
      </div>
      <div className='flex flex-col gap-2 px-5 py-4'>
        <Skeleton className='h-4 w-24 rounded-md' />
        <Skeleton className='h-4 w-full rounded-md' />
        <Skeleton className='h-4 w-5/6 rounded-md' />
      </div>
    </div>
  )
}

/** 权限空态（403，不跳登录；无「重试」按钮——非请求失败） */
function PermissionEmpty() {
  return (
    <Empty className='border-dashed rounded-xl border px-6 py-12'>
      <EmptyHeader>
        <EmptyMedia variant='icon'>
          <Lock aria-hidden='true' className='size-4' />
        </EmptyMedia>
        <EmptyTitle>无法查看排行数据</EmptyTitle>
        <EmptyDescription>当前账号无排行查看权限，请登录或联系管理员。</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}

/** 错误态（请求失败，含「重试」按钮） */
function ErrorState(props: { message: string; onRetry: () => void }) {
  return (
    <Empty className='border-dashed rounded-xl border px-6 py-12'>
      <EmptyHeader>
        <EmptyMedia variant='icon'>
          <RefreshCw aria-hidden='true' className='size-4' />
        </EmptyMedia>
        <EmptyTitle>排行加载失败</EmptyTitle>
        <EmptyDescription>{props.message}</EmptyDescription>
        <EmptyContent>
          <Button variant='outline' size='sm' onClick={props.onRetry}>
            重试
          </Button>
        </EmptyContent>
      </EmptyHeader>
    </Empty>
  )
}

/** 空态（查询成功但 0 行；有计算权限加「立即计算」，无权限补提示） */
function EmptyState(props: { canCompute: boolean; onCompute: () => void }) {
  return (
    <Empty className='border-dashed rounded-xl border px-6 py-12'>
      <EmptyHeader>
        <EmptyMedia variant='icon'>
          <Trophy aria-hidden='true' className='size-4' />
        </EmptyMedia>
        <EmptyTitle>暂无排行数据</EmptyTitle>
        <EmptyDescription>
          {props.canCompute
            ? '尚未计算排行，或当前筛选条件下没有数据。'
            : '尚未计算排行，或当前筛选条件下没有数据。请联系管理员计算排行。'}
        </EmptyDescription>
        {props.canCompute && (
          <EmptyContent>
            <Button size='sm' onClick={props.onCompute}>
              立即计算
            </Button>
          </EmptyContent>
        )}
      </EmptyHeader>
    </Empty>
  )
}
