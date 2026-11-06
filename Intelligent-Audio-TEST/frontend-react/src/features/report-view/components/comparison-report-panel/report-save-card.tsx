/**
 * 报告保存卡（15_报告域.md §3.4，analysis-conclusion-card 对位）。
 * 报告名称 Input + 报告描述 Textarea + 状态徽标；保存 → PUT /reports/{id}。
 */
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { useReportActions } from '@/application/reports/use-report-actions'
import type { ReportDetailData } from '@/domain/models/report'
import { getReportStatusMeta } from '@/features/reports/constants'

export function ReportSaveCard({ report }: { report: ReportDetailData }) {
  const [name, setName] = useState(report.name)
  const [description, setDescription] = useState(report.description ?? '')
  const [saving, setSaving] = useState(false)
  const statusMeta = getReportStatusMeta(report.status)
  const { rename } = useReportActions()

  const handleSave = async () => {
    if (!name.trim() || saving) return
    setSaving(true)
    try {
      await rename(report.id, { name: name.trim(), description })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className='bg-card rounded-2xl border shadow-xs p-4'>
      <div className='flex items-center justify-between gap-2'>
        <p className='text-sm font-semibold'>报告保存</p>
        <StatusBadge label={statusMeta.label} variant={statusMeta.variant} size='sm' />
      </div>
      <div className='mt-3 space-y-2'>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder='请输入报告名称'
          className='h-9'
        />
        <Textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder='请输入报告描述'
          className='min-h-16 max-h-40 field-sizing-content'
        />
      </div>
      <div className='mt-3 flex items-center gap-2'>
        <Button size='sm' disabled={!name.trim() || saving} onClick={() => void handleSave()}>
          {saving ? '保存中...' : '保存'}
        </Button>
        {report.type === 'secondary_comparison' && (
          <Badge variant='outline'>二次对比</Badge>
        )}
      </div>
    </div>
  )
}
