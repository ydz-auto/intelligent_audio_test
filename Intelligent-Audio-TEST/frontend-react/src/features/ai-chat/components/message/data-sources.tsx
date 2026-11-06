/**
 * 数据来源折叠（interfaces 层 ai-chat/message；08_AI对话页.md §3.4）：
 * 「已使用 {n} 处数据来源」+ sourceRef 列表（报告 ID + 指标 ID + 数据版本）；
 * 无法证明来源的数值标 Badge warning「待核实」，不得写入定稿数字（Studio §15.8 照搬）。
 */
import { Badge } from '@/components/ui/badge'
import {
  Source,
  Sources,
  SourcesContent,
  SourcesTrigger,
} from '@/components/ai-elements/sources'
import type { ChatSourceRef } from '@/domain/models/aiChat'

type DataSourcesProps = {
  refs: ChatSourceRef[]
  className?: string
}

export function DataSources({ refs, className }: DataSourcesProps) {
  if (refs.length === 0) return null

  return (
    <Sources className={className}>
      <SourcesTrigger count={refs.length} />
      <SourcesContent>
        {refs.map((ref, index) => (
          <Source
            href={`/reports/${ref.reportId}`}
            key={`${ref.reportId}-${ref.metricId ?? index}`}
          >
            <span className='flex items-center gap-2'>
              <span className='block font-medium'>
                报告 {ref.reportId}
                {ref.metricId ? ` · ${ref.metricId}` : ''}
              </span>
              {ref.dataVersion && (
                <Badge
                  className='font-mono text-[10px]'
                  variant='outline'
                >
                  数据版本 {ref.dataVersion}
                </Badge>
              )}
              {ref.verified === false && (
                <Badge className='text-[10px]' variant='warning'>
                  待核实
                </Badge>
              )}
            </span>
          </Source>
        ))}
      </SourcesContent>
    </Sources>
  )
}
