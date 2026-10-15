/**
 * 具体用例展开详情（规范 §4.7 TestCaseReportDetail 平移）：
 * 音频信息 + ASR 识别（参考/各资源结果）+ 翻译信息 + 评估指标表 + 详细日志 pre。
 */
import { FileAudio, Languages, MicVocal, ScrollText } from 'lucide-react'
import type { ReactNode } from 'react'

import type { ReportCaseItem } from '@/domain/models/report'

function DetailSection({
  icon,
  title,
  children,
}: {
  icon: ReactNode
  title: string
  children: ReactNode
}) {
  return (
    <div className='space-y-1.5'>
      <div className='flex items-center gap-1.5 text-xs font-medium'>
        {icon}
        {title}
      </div>
      {children}
    </div>
  )
}

export function ReportCaseDetail({ caseItem }: { caseItem: ReportCaseItem }) {
  return (
    <div className='space-y-3 border-t pt-3 text-sm'>
      {caseItem.description && (
        <p className='text-muted-foreground text-xs leading-relaxed'>
          {caseItem.description}
        </p>
      )}

      {caseItem.audios.length > 0 && (
        <DetailSection icon={<FileAudio className='size-3.5' />} title='音频信息'>
          <ul className='space-y-1'>
            {caseItem.audios.map((audio) => (
              <li
                key={String(audio.audio_id)}
                className='text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs'
              >
                <span className='font-mono'>{audio.audio_name}</span>
                <span>{audio.audio_type === 'wakeword' ? '唤醒词' : audio.audio_type}</span>
                {audio.device_name && <span>· {audio.device_name}</span>}
                {audio.spl != null && <span>· SPL {audio.spl}dB</span>}
                {audio.noise_spl != null && <span>· 噪声 {audio.noise_spl}dB</span>}
              </li>
            ))}
          </ul>
        </DetailSection>
      )}

      {caseItem.asr && (
        <DetailSection icon={<MicVocal className='size-3.5' />} title='ASR 识别'>
          <div className='bg-muted/30 space-y-1 rounded-lg px-3 py-2 text-xs'>
            <div>
              <span className='text-muted-foreground'>参考文本：</span>
              {caseItem.asr.reference}
            </div>
            {caseItem.asr.results &&
              Object.entries(caseItem.asr.results).map(([resource, text]) => (
                <div key={resource} className='flex gap-1'>
                  <span className='text-muted-foreground shrink-0'>{resource}：</span>
                  <span>{text}</span>
                </div>
              ))}
          </div>
        </DetailSection>
      )}

      {caseItem.translation && (
        <DetailSection icon={<Languages className='size-3.5' />} title='翻译信息'>
          <div className='bg-muted/30 space-y-1 rounded-lg px-3 py-2 text-xs'>
            <div>
              <span className='text-muted-foreground'>方向：</span>
              {caseItem.translation.direction}
            </div>
            <div>
              <span className='text-muted-foreground'>参考译文：</span>
              {caseItem.translation.reference}
            </div>
            {caseItem.translation.results &&
              Object.entries(caseItem.translation.results).map(([resource, text]) => (
                <div key={resource} className='flex gap-1'>
                  <span className='text-muted-foreground shrink-0'>{resource}：</span>
                  <span>{text}</span>
                </div>
              ))}
          </div>
        </DetailSection>
      )}

      {caseItem.metrics.length > 0 && (
        <DetailSection icon={<MicVocal className='size-3.5' />} title='评估指标'>
          <div className='overflow-x-auto rounded-lg border'>
            <table className='w-full text-xs'>
              <thead>
                <tr className='text-muted-foreground border-b bg-muted/30'>
                  <th className='px-3 py-1.5 text-left font-medium'>指标</th>
                  <th className='px-3 py-1.5 text-right font-medium'>值</th>
                </tr>
              </thead>
              <tbody>
                {caseItem.metrics.map((metric) => (
                  <tr key={metric.metric} className='border-b last:border-0'>
                    <td className='px-3 py-1.5'>{metric.metric}</td>
                    <td className='px-3 py-1.5 text-right font-mono tabular-nums'>
                      {metric.value.toFixed(metric.decimal_places ?? 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DetailSection>
      )}

      {caseItem.logs ? (
        <DetailSection icon={<ScrollText className='size-3.5' />} title='详细日志'>
          <pre className='bg-muted/30 overflow-x-auto rounded-lg px-3 py-2 font-mono text-xs leading-relaxed whitespace-pre-wrap'>
            {caseItem.logs}
          </pre>
        </DetailSection>
      ) : (
        <DetailSection icon={<ScrollText className='size-3.5' />} title='详细日志'>
          <span className='text-muted-foreground text-xs'>暂无日志信息</span>
        </DetailSection>
      )}
    </div>
  )
}
