/**
 * 块三：执行结果（15_报告域.md §3.5.3，TestCaseReportDetail 块三对位）。
 * 参考数据（referenceParams text）+ 子分区按数据有无渲染：用例参数/评估结果/设备·API 执行结果
 * /时间轴对比/音频时间轴/结果音频。
 */
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import type { ReportCaseItem, ReportDetailData, ReportReferenceParam } from '@/domain/models/report'

import { ResultField } from './result-field'
import { TimelineComparison } from './timeline-comparison'
import { AudioTimeline } from './audio-timeline'
import { AudioPlayerModal, type AudioItemMeta } from './audio-player-modal'

export function ExecutionResults({
  caseItem,
  report,
}: {
  caseItem: ReportCaseItem
  report: ReportDetailData
}) {
  const [playingAudio, setPlayingAudio] = useState<AudioItemMeta>()

  const referenceFields = useMemo(
    () =>
      Object.entries(caseItem.referenceParams ?? {})
        .filter(([, p]) => (p as ReportReferenceParam).type === 'text')
        .map(([code, p]) => ({
          label: ((p as ReportReferenceParam).code ?? code) || code,
          value: (p as ReportReferenceParam).value ?? (p as ReportReferenceParam).text ?? '',
        })),
    [caseItem.referenceParams]
  )

  const hasTimeline = (caseItem.algorithmResults ?? []).some((r) =>
    ['rttm', 'stm', 'json'].includes(r.paramType ?? '')
  )
  const hasAudio = (caseItem.audios?.length ?? 0) > 0

  const dimensionFields = useMemo(() => {
    const map = new Map<string, { label: string; value: unknown; type?: string }[]>()
    for (const result of caseItem.algorithmResults ?? []) {
      const dim = result.dimensionName ?? '_general'
      const list = map.get(dim) ?? []
      list.push({ label: result.label ?? result.paramCode, value: result.value, type: result.paramType })
      map.set(dim, list)
    }
    return [...map.entries()]
  }, [caseItem.algorithmResults])

  return (
    <div className='space-y-3'>
      <p className='text-sm font-semibold'>执行结果</p>

      {/* 参考数据 */}
      {referenceFields.length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>参考数据</p>
          <div className='rounded-lg border'>
            {referenceFields.map((field) => (
              <ResultField key={field.label} label={field.label} value={field.value} />
            ))}
          </div>
        </div>
      )}

      {/* 用例参数（§3.5.4：算法输入参数 caseParams，按轮次展示；P2-8 不再误用 referenceParams） */}
      {caseItem.caseParams && Object.keys(caseItem.caseParams).length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>用例参数</p>
          <div className='rounded-lg border'>
            {Object.entries(caseItem.caseParams).map(([code, p]) => (
              <ResultField
                key={code}
                label={(p as ReportReferenceParam).code ?? code}
                value={(p as ReportReferenceParam).value}
                type={(p as ReportReferenceParam).type}
              />
            ))}
          </div>
        </div>
      )}

      {/* 评估结果（§3.5.5，按维度分组） */}
      {dimensionFields.length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>评估结果</p>
          {dimensionFields.map(([dim, fields]) => (
            <div key={dim} className='mb-2'>
              <p className='text-muted-foreground text-xs'>{dim === '_general' ? '其他结果' : dim}</p>
              <div className='mt-1 rounded-lg border'>
                {fields.map((field, i) => (
                  <ResultField
                    key={i}
                    label={field.label}
                    value={field.value}
                    type={field.type}
                    onPlayAudio={(v) =>
                      setPlayingAudio({
                        audio_id: String(v),
                        audio_name: field.label,
                        audio_type: 'result',
                      })
                    }
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 设备/API 执行结果（§3.5.6） */}
      {caseItem.results.length > 0 && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>设备/API 执行结果</p>
          <div className='rounded-lg border'>
            {caseItem.results.map((r) => (
              <div key={r.resource} className='flex items-center justify-between gap-2 border-b px-3 py-1.5 text-xs last:border-0'>
                <span className='font-medium'>{r.resource}</span>
                <span className='text-muted-foreground'>
                  {statusLabel(r.status)}
                  {r.startTime && <span className='ms-2 font-mono'>{r.startTime}</span>}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 时间轴对比（§3.3.9） */}
      {hasTimeline && <TimelineComparison caseItem={caseItem} report={report} />}

      {/* 音频时间轴（§3.5.7） */}
      {hasAudio && <AudioTimeline audioList={caseItem.audios ?? []} />}

      {/* 结果音频 */}
      {caseItem.audios?.some((a) => a.url) && (
        <div>
          <p className='text-muted-foreground mb-1 text-xs font-medium'>结果音频</p>
          <div className='flex flex-wrap gap-2'>
            {(caseItem.audios ?? []).filter((a) => a.url).map((audio) => (
              <Badge key={String(audio.audio_id)} variant='outline'>
                {audio.audio_name ?? `音频 ${audio.audio_id}`}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <AudioPlayerModal
        open={playingAudio !== undefined}
        onOpenChange={(open) => {
          if (!open) setPlayingAudio(undefined)
        }}
        audio={playingAudio}
      />
    </div>
  )
}

function statusLabel(status?: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    failed: '执行失败',
    skipped: '已跳过',
    pending: '排队中',
    'in-progress': '执行中',
  }
  return map[status ?? ''] ?? status ?? '—'
}
