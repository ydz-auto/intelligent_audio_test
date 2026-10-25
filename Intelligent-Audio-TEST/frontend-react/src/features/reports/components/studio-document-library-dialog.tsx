/**
 * Report Studio 文档库 Dialog（INT-1766 D8；report:read）。
 *
 * 全局文档库入口（报告中心「更多操作 → 报告文档」）：不限定 report_id，列表按 `source_type`
 * 区分展示（全部 / 上传文档 / Agent 总结 / 平台报告文档）。
 * 报告详情页与任务详情页的嵌入式文档区见 `studio-document-section.tsx`——同一套列表行 /
 * 正文查看器，那两处固定带 `report_id`（平台报告详情页再叠加 `source_type=platform_report`，
 * 上传文档不混进平台报告文档列表）。
 */
import { Upload } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useStudioDocuments } from '@/application/reports/use-report-studio'
import { StudioSourceType, type StudioSourceTypeValue } from '@/domain/models/report-studio'
import { UploadReportDialog } from './modals/upload-report-dialog'
import { StudioDocumentDetail, StudioDocumentRow } from './studio-document-section'

const ALL = '__all__'

const SOURCE_FILTERS: Array<{ value: string; label: string }> = [
  { value: ALL, label: '全部文档' },
  { value: StudioSourceType.UPLOADED_FILE, label: '上传文档' },
  { value: StudioSourceType.AGENT_SUMMARY, label: 'Agent 总结' },
  { value: StudioSourceType.PLATFORM_REPORT, label: '平台报告文档' },
]

interface StudioDocumentLibraryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function StudioDocumentLibraryDialog({
  open,
  onOpenChange,
}: StudioDocumentLibraryDialogProps) {
  const { hasPermission } = usePermissions()
  const [sourceFilter, setSourceFilter] = useState<string>(ALL)
  const [activeDocId, setActiveDocId] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setSourceFilter(ALL)
      setActiveDocId(null)
      setNotice(null)
    }
  }, [open])

  const query = useMemo(
    () => ({
      sourceType:
        sourceFilter === ALL ? undefined : (sourceFilter as StudioSourceTypeValue),
      limit: 100,
    }),
    [sourceFilter]
  )
  const listQuery = useStudioDocuments(query, { enabled: open })

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className='flex h-[80vh] flex-col sm:max-w-3xl'>
          <DialogHeader>
            <DialogTitle>报告文档</DialogTitle>
            <DialogDescription>
              Report Studio 文档库：上传的独立报告、搬运回来的 Agent 总结与平台报告文档按来源区分。
            </DialogDescription>
          </DialogHeader>

          <div className='flex items-center gap-2'>
            <Select
              items={SOURCE_FILTERS}
              value={sourceFilter}
              onValueChange={(value) => {
                setSourceFilter(value ?? ALL)
                setActiveDocId(null)
              }}
            >
              <SelectTrigger className='w-44'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCE_FILTERS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className='text-muted-foreground text-xs'>
              共 {listQuery.data?.total ?? 0} 份
            </span>
            {hasPermission('report:studio:create') && (
              <Button
                className='ml-auto'
                size='sm'
                variant='outline'
                onClick={() => setUploadOpen(true)}
              >
                <Upload data-icon='inline-start' />
                上传独立报告
              </Button>
            )}
          </div>

          {notice && <p className='text-muted-foreground text-xs'>{notice}</p>}

          <div className='flex min-h-0 flex-1 gap-3'>
            <div className='w-64 shrink-0 overflow-y-auto rounded-md border'>
              {listQuery.isLoading ? (
                <p className='text-muted-foreground flex items-center gap-2 p-3 text-sm'>
                  <Spinner className='size-4' /> 加载中…
                </p>
              ) : listQuery.isError ? (
                <p className='text-destructive p-3 text-sm'>文档列表加载失败</p>
              ) : (listQuery.data?.items.length ?? 0) === 0 ? (
                <p className='text-muted-foreground p-3 text-sm'>暂无文档</p>
              ) : (
                <ul className='divide-y'>
                  {listQuery.data?.items.map((doc) => (
                    <li key={doc.docId}>
                      <StudioDocumentRow
                        active={activeDocId === doc.docId}
                        doc={doc}
                        onClick={() => setActiveDocId(doc.docId)}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className='flex min-h-0 min-w-0 flex-1 flex-col'>
              {activeDocId ? (
                <StudioDocumentDetail docId={activeDocId} />
              ) : (
                <p className='text-muted-foreground m-auto text-sm'>从左侧选择一份文档查看</p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant='outline' onClick={() => onOpenChange(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <UploadReportDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={(title) => {
          setNotice(`已上传「${title}」，文档列表已刷新`)
          setSourceFilter(StudioSourceType.UPLOADED_FILE)
        }}
      />
    </>
  )
}
