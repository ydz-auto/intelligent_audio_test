/**
 * 时间轴对比（15_报告域.md §3.3.9，TimelineComparison 对位）。
 * 标题 + 缩放控制（缩小/scale×/放大/重置）+ 资源下拉 + 说话人筛选；每说话人行 = 参考行 + 结果行；
 * 底部时间刻度。空态「暂无时间轴数据」。
 */
import { Minus, Plus, RotateCcw } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTimelineComparison } from '@/application/report-view/use-timeline-comparison'
import type { ReportCaseItem, ReportDetailData } from '@/domain/models/report'

export function TimelineComparison({
  caseItem,
  report,
}: {
  caseItem: ReportCaseItem
  report: ReportDetailData
}) {
  const { scale, zoom, resetZoom, selectedSpeaker, setSelectedSpeaker, build } = useTimelineComparison()
  const [resource, setResource] = useState('全部')

  const fieldMappingRef = report.summary.field_mappings?.[0]?.algorithmType.reference
  const timeline = useMemo(
    () => build(caseItem.algorithmResults ?? [], caseItem.referenceParams, fieldMappingRef),
    [caseItem.algorithmResults, caseItem.referenceParams, fieldMappingRef] // eslint-disable-line react-hooks/exhaustive-deps
  )

  if (!timeline) {
    return (
      <div className='text-muted-foreground flex h-20 items-center justify-center rounded-lg border text-xs'>
        暂无时间轴数据
      </div>
    )
  }

  const speakers = timeline.speakers.filter((s) => s === '全部' || selectedSpeaker === '全部' || s === selectedSpeaker)
  const resources = [
    '全部',
    ...new Set([
      ...caseItem.results.map((r) => r.resource),
      ...timeline.resultSegments.map((s) => s.resource ?? '').filter(Boolean),
    ]),
  ]

  const maxDuration = timeline.effectiveDuration * scale

  return (
    <div className='space-y-2'>
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <p className='text-sm font-semibold'>时间轴对比</p>
        <div className='flex items-center gap-1'>
          <Button variant='ghost' size='sm' className='h-7 px-1.5' aria-label='缩小' onClick={() => zoom(0.8)}>
            <Minus aria-hidden='true' className='size-3.5' />
          </Button>
          <span className='text-muted-foreground w-10 text-center text-xs tabular-nums'>{scale.toFixed(1)}x</span>
          <Button variant='ghost' size='sm' className='h-7 px-1.5' aria-label='放大' onClick={() => zoom(1.25)}>
            <Plus aria-hidden='true' className='size-3.5' />
          </Button>
          <Button variant='ghost' size='sm' className='h-7 px-1.5' aria-label='重置' onClick={resetZoom}>
            <RotateCcw aria-hidden='true' className='size-3.5' />
          </Button>
        </div>
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <Select value={resource} onValueChange={(v) => setResource(v ?? '')}>
          <SelectTrigger className='h-8 w-44 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {resources.map((r) => (
              <SelectItem key={r} value={r}>{r === '全部' ? '全部资源' : r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={selectedSpeaker} onValueChange={(v) => setSelectedSpeaker(v ?? '全部')}>
          <SelectTrigger className='h-8 w-32 text-xs'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {timeline.speakers.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className='overflow-hidden rounded-lg border'>
        <div className='overflow-x-auto'>
          <div className='min-w-[560px] p-3'>
            {speakers.map((speaker) => {
              if (speaker === '全部') return null
              const refs = timeline.referenceSegments.filter((s) => s.speaker === speaker)
              const results = timeline.resultSegments.filter(
                (s) =>
                  s.speaker === speaker &&
                  (resource === '全部' || s.resource === resource)
              )
              return (
                <div key={speaker} className='space-y-1'>
                  <p className='text-muted-foreground text-xs font-medium'>{speaker}</p>
                  <div className='space-y-1'>
                    <SegmentRow label='参考' segments={refs} maxDuration={maxDuration} tone='bg-muted' />
                    <SegmentRow
                      label='结果'
                      segments={results}
                      maxDuration={maxDuration}
                      tone='bg-primary/40'
                      matchTone='bg-primary/70'
                    />
                  </div>
                </div>
              )
            })}
            <div className='text-muted-foreground mt-2 flex justify-between text-[10px] font-mono tabular-nums'>
              <span>0s</span>
              <span>{maxDuration.toFixed(1)}s</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function SegmentRow({
  label,
  segments,
  maxDuration,
  tone,
  matchTone,
}: {
  label: string
  segments: { start: number; end: number; text: string; isMatch?: boolean }[]
  maxDuration: number
  tone: string
  matchTone?: string
}) {
  return (
    <div className='flex items-center gap-2 text-xs'>
      <span className='text-muted-foreground w-8 shrink-0'>{label}</span>
      <div className='relative h-6 flex-1 overflow-hidden rounded bg-muted/30'>
        {segments.length === 0 && <span className='text-muted-foreground px-2 text-[10px]'>无数据</span>}
        {segments.map((seg, i) => (
          <div
            key={i}
            className={(seg.isMatch ? (matchTone ?? tone) : tone) + ' absolute top-1 h-4 overflow-hidden rounded-sm px-1.5 text-[10px] leading-4'}
            style={{
              left: `${(seg.start / maxDuration) * 100}%`,
              width: `${((seg.end - seg.start) / maxDuration) * 100}%`,
            }}
            title={seg.text}
          >
            <span className='truncate'>{seg.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
