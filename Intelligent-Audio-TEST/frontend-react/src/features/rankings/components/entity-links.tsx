/**
 * 榜单实体链接（对位 newAPI entity-links.tsx——榜单即导航）。
 * SubjectLink：主体名常驻细下划线，点击=本页 subjectName 筛选（同页联动）；
 * ReportLink：实测轨行尾「查看报告」→ /report/{reportId}，仅 report:read 持有者渲染。
 */
import { Link, useNavigate } from '@tanstack/react-router'
import { FileText } from 'lucide-react'

import { useBenchmarkAccess } from '@/application/rankings/useBenchmarkAccess'
import { cn } from '@/lib/utils'

export function SubjectLink(props: {
  subjectName: string
  className?: string
}) {
  const navigate = useNavigate()

  return (
    <button
      type='button'
      onClick={() =>
        void navigate({
          to: '/rankings',
          search: (prev) => ({ ...prev, subjectName: props.subjectName }),
        })
      }
      title='按此主体筛选排行'
      className={cn(
        'text-foreground decoration-foreground/30 hover:decoration-foreground cursor-pointer underline decoration-1 underline-offset-4',
        props.className
      )}
    >
      {props.subjectName}
    </button>
  )
}

export function ReportLink(props: {
  reportId: number
  className?: string
}) {
  const { canReadReport } = useBenchmarkAccess()
  if (!canReadReport) return null

  return (
    <Link
      to='/report/$reportId'
      params={{ reportId: String(props.reportId) }}
      className={cn(
        'text-primary inline-flex items-center gap-1 text-xs font-medium hover:underline',
        props.className
      )}
    >
      <FileText aria-hidden='true' className='size-3' />
      查看报告
    </Link>
  )
}
