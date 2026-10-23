/**
 * 排行榜筛选行（14_benchmark排行.md §4.3/§5.2）：测试集 / 指标 / 数据来源 Select
 * + 主体搜索联想（防抖 300ms，键盘可选）+ 重置 + 立即计算（RBAC 门控）。
 * 全部筛选状态由页面层写 URL search；本组件只负责 UI 与本地输入态。
 */
import { LoaderCircle, Search, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { useRankingSubjects } from '@/application/rankings/useRankingSubjects'
import { useBenchmarkAccess } from '@/application/rankings/useBenchmarkAccess'
import { useMetricMappings } from '@/application/rankings/useMetricMappings'
import { hasActiveFilters } from '@/application/rankings/rankingFilters'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import type { RankingFilters } from '@/domain/models/benchmark'
import { cn } from '@/lib/utils'

const SOURCE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: '', label: '全部来源' },
  { value: 'platform_test', label: '平台实测' },
  { value: 'external_import', label: '外部基线' },
]

const METRIC_ALL_LABEL = '全部指标'

export function RankingFiltersBar(props: {
  filters: RankingFilters
  suites: string[]
  onFilterChange: (patch: Partial<RankingFilters>) => void
  onReset: () => void
  isFetching: boolean
  /** 触发重算（确认弹窗由页面层统一持有，空态「立即计算」共用同一链路） */
  onCompute: () => void
  /** 重算 mutation 进行中（按钮 loading 态） */
  computePending: boolean
}) {
  const { filters, suites, onFilterChange, onReset, isFetching, onCompute, computePending } = props
  const { mappings, isFailed: mappingsFailed } = useMetricMappings()
  const { canCompute } = useBenchmarkAccess()

  // INT-1619：Select.Root 的 items 是 value↔label 表，闭合态触发器据它取中文标签；
  // 不传时 base-ui 的 Select.Value 直接渲染原始值（ENV_UNDERSTAND_SCORE / platform_test）。
  const metricItems = useMemo(
    () => [
      { value: '', label: METRIC_ALL_LABEL },
      ...mappings.map((mapping) => ({
        value: mapping.metricCode,
        label: mapping.metricName,
      })),
    ],
    [mappings]
  )
  const sourceItems = useMemo(() => [...SOURCE_OPTIONS], [])

  // 主体搜索：本地输入态 + 防抖 300ms 写 URL
  const [subjectInput, setSubjectInput] = useState(filters.subjectName)
  useEffect(() => {
    if (subjectInput === filters.subjectName) return
    const timer = setTimeout(() => {
      onFilterChange({ subjectName: subjectInput.trim() })
    }, 300)
    return () => clearTimeout(timer)
  }, [subjectInput, filters.subjectName, onFilterChange])

  // 外部把 subjectName 清空（重置导航/URL 回退）时同步清空本地输入——
  // 防抖 effect 不再把旧输入回灌 URL（P2-1 修复：subjectInput 不随 props 同步的复活路径）
  useEffect(() => {
    setSubjectInput((prev) =>
      filters.subjectName === '' && prev !== '' ? '' : prev
    )
  }, [filters.subjectName])

  const [subjectOpen, setSubjectOpen] = useState(false)
  const { subjects } = useRankingSubjects(filters.suite, subjectInput.trim() !== '')
  const suggestions = useMemo(() => {
    const query = subjectInput.trim()
    if (!query) return []
    return subjects.filter((name) => name.includes(query)).slice(0, 8)
  }, [subjects, subjectInput])

  // 主体联想：键盘上下选择 / 回车确认 / Escape 关闭
  const [activeIndex, setActiveIndex] = useState(-1)
  const handleSubjectKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((prev) => (prev + 1) % Math.max(suggestions.length, 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((prev) =>
        prev <= 0 ? suggestions.length - 1 : prev - 1
      )
    } else if (event.key === 'Enter') {
      const pick = suggestions[activeIndex]
      if (pick) {
        event.preventDefault()
        setSubjectInput(pick)
        setSubjectOpen(false)
        onFilterChange({ subjectName: pick })
      }
    } else if (event.key === 'Escape') {
      setSubjectOpen(false)
    }
  }

  // 重置：先清本地输入与联想（取消防抖回灌），再走页面层 URL 重置
  const handleReset = () => {
    setSubjectInput('')
    setSubjectOpen(false)
    setActiveIndex(-1)
    onReset()
  }

  const showSuggestion = subjectOpen && suggestions.length > 0

  return (
    <div className='flex flex-wrap items-center gap-2'>
      {/* 测试集 */}
      <Select
        value={filters.suite}
        onValueChange={(value) => onFilterChange({ suite: value ?? '' })}
      >
        <SelectTrigger size='sm' className='w-40' aria-label='测试集'>
          <SelectValue placeholder='全部测试集' />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value=''>全部测试集</SelectItem>
          {suites.map((suite) => (
            <SelectItem key={suite} value={suite}>
              {suite}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* 指标（映射接口失败退化为纯文本输入，不打断页面） */}
      {mappingsFailed ? (
        <Input
          aria-label='指标代码'
          placeholder='指标代码'
          value={filters.metricCode}
          onChange={(e) => onFilterChange({ metricCode: e.target.value })}
          className='h-8 w-40'
        />
      ) : (
        <Select
          value={filters.metricCode}
          items={metricItems}
          onValueChange={(value) => onFilterChange({ metricCode: value ?? '' })}
        >
          <SelectTrigger size='sm' className='w-40' aria-label='指标'>
            <SelectValue placeholder={METRIC_ALL_LABEL} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value=''>{METRIC_ALL_LABEL}</SelectItem>
            {mappings.map((mapping) => (
              <SelectItem key={mapping.metricCode} value={mapping.metricCode}>
                {mapping.metricName}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {/* 数据来源 */}
      <Select
        value={filters.source}
        items={sourceItems}
        onValueChange={(value) => onFilterChange({ source: value ?? '' })}
      >
        <SelectTrigger size='sm' className='w-32' aria-label='数据来源'>
          <SelectValue placeholder='全部来源' />
        </SelectTrigger>
        <SelectContent>
          {SOURCE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* 搜索主体（联想下拉） */}
      <div className='relative min-w-0 basis-52'>
        <Search
          aria-hidden='true'
          className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
        />
        <Input
          aria-label='搜索主体'
          aria-expanded={showSuggestion}
          value={subjectInput}
          onChange={(e) => {
            setSubjectInput(e.target.value)
            setSubjectOpen(true)
            setActiveIndex(-1)
          }}
          onFocus={() => setSubjectOpen(true)}
          onBlur={() => setTimeout(() => setSubjectOpen(false), 150)}
          onKeyDown={handleSubjectKeyDown}
          placeholder='搜索主体名称…'
          className='h-8 pl-8'
        />
        {showSuggestion && (
          <ul
            role='listbox'
            aria-label='主体联想'
            className='bg-popover text-popover-foreground border-border absolute z-20 mt-1 w-full overflow-hidden rounded-lg border p-1 shadow-md'
          >
            {suggestions.map((name, index) => (
              <li
                key={name}
                role='option'
                aria-selected={index === activeIndex}
                className={cn(
                  'flex cursor-pointer items-center rounded-md px-2.5 py-1.5 text-sm',
                  index === activeIndex ? 'bg-muted' : 'hover:bg-muted/60'
                )}
                onMouseDown={(e) => {
                  e.preventDefault()
                  setSubjectInput(name)
                  setSubjectOpen(false)
                  onFilterChange({ subjectName: name })
                }}
              >
                {name}
              </li>
            ))}
            {suggestions.length === 0 && (
              <li className='text-muted-foreground px-2.5 py-1.5 text-sm'>
                未找到匹配的主体
              </li>
            )}
          </ul>
        )}
      </div>

      <div className='ms-auto flex items-center gap-1.5'>
        {isFetching && (
          <LoaderCircle
            aria-hidden='true'
            className='text-muted-foreground size-4 animate-spin'
          />
        )}
        {hasActiveFilters(filters) && (
          <Button
            variant='ghost'
            size='sm'
            onClick={handleReset}
            aria-label='重置'
          >
            <RotateCcw aria-hidden='true' className='size-3.5' />
            重置
          </Button>
        )}
        {canCompute && (
          <Button size='sm' onClick={onCompute}>
            {computePending ? (
              <>
                <Spinner aria-hidden='true' />
                计算中…
              </>
            ) : (
              '立即计算'
            )}
          </Button>
        )}
      </div>
    </div>
  )
}
