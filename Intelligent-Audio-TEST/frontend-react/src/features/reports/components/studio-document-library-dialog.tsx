/**
 * Report Studio 文档库 Dialog（INT-1766 D8；report:read）。
 *
 * 列表按 `source_type` 区分展示（平台报告文档 / 上传文档 / Agent 总结），默认「全部」，
 * 可按来源筛选；平台报告详情页的文档区若接入，必须带 `report_id + source_type=platform_report`
 * （见 application/reports/use-report-studio.ts，上传文档不会混进平台报告文档列表）。
 *
 * 打开文档：
 * - md：Markdown 正文可读可编辑（PUT 乐观锁），版本号递增；
 * - html / pptx：经鉴权接口取 Blob，用 `<iframe sandbox="allow-scripts">` 预览（不加
 *   allow-same-origin，后端同时下发 nosniff + 沙箱 CSP）或下载原件；
 * - 图表降级：`chart_refs` 非空且 `report_id` 为空（3c 搬运后源报告缺失）时，图表区
 *   提示「需重新绑定报告」，正文照常展示，不白屏（设计 §6.3-5）。
 */
import { Download, FileText, History, Pencil, Save, Upload } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
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
import { Textarea } from '@/components/ui/textarea'
import { Markdown } from '@/components/ui/markdown'
import { usePermissions } from '@/application/hooks/use-permissions'
import {
  useRestoreStudioDocumentVersion,
  useStudioDocument,
  useStudioDocumentVersions,
  useStudioDocuments,
  useUpdateStudioDocument,
} from '@/application/reports/use-report-studio'
import {
  STUDIO_SOURCE_TYPE_LABEL,
  StudioSourceType,
  needsChartRebind,
  type StudioDocument,
  type StudioSourceTypeValue,
} from '@/domain/models/report-studio'
import { fetchStudioSourceBlob } from '@/infrastructure/api/reportStudioApi'
import { UploadReportDialog } from './modals/upload-report-dialog'

const ALL = '__all__'
/** 版本下拉的「当前版本」哨兵值（Select 不接受空字符串 as value） */
const CURRENT = '__current__'

const SOURCE_FILTERS: Array<{ value: string; label: string }> = [
  { value: ALL, label: '全部文档' },
  { value: StudioSourceType.UPLOADED_FILE, label: '上传文档' },
  { value: StudioSourceType.AGENT_SUMMARY, label: 'Agent 总结' },
  { value: StudioSourceType.PLATFORM_REPORT, label: '平台报告文档' },
]

function formatSize(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function compactDate(value: string | null): string {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

/** html / pptx 上传件预览：鉴权取 Blob → sandbox iframe（不加 allow-same-origin） */
function SourceFilePreview({ doc }: { doc: StudioDocument }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let revoked: string | null = null
    let cancelled = false
    setUrl(null)
    setError(null)
    setLoading(true)
    void fetchStudioSourceBlob(doc.docId)
      .then((blob) => {
        if (cancelled) return
        revoked = URL.createObjectURL(
          new Blob([blob], {
            type: doc.sourceFormat === 'html' ? 'text/html' : 'application/octet-stream',
          })
        )
        setUrl(revoked)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '源文件读取失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      if (revoked) URL.revokeObjectURL(revoked)
    }
  }, [doc.docId, doc.sourceFormat])

  if (loading) {
    return (
      <p className='text-muted-foreground flex items-center gap-2 text-sm'>
        <Spinner className='size-4' /> 正在加载源文件…
      </p>
    )
  }
  if (error || !url) {
    return <p className='text-destructive text-sm'>{error ?? '源文件不可用'}</p>
  }
  if (doc.sourceFormat === 'html') {
    return (
      <iframe
        className='bg-background h-[420px] w-full rounded-md border'
        sandbox='allow-scripts'
        src={url}
        title={doc.title}
      />
    )
  }
  return (
    <div className='space-y-2 text-sm'>
      <p className='text-muted-foreground'>
        PPTX 为二进制文件，不做在线格式转换（设计 §6.2），可下载后用本机 Office 打开。
      </p>
      <a className='text-primary inline-flex items-center gap-1 underline' download={`${doc.title}.pptx`} href={url}>
        <Download className='size-4' />
        下载原件
      </a>
    </div>
  )
}

function DocumentDetail({ docId }: { docId: string }) {
  const { hasPermission } = usePermissions()
  const docQuery = useStudioDocument(docId)
  const versionsQuery = useStudioDocumentVersions(docId)
  const update = useUpdateStudioDocument()
  const restore = useRestoreStudioDocumentVersion()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [viewVersion, setViewVersion] = useState<string>(CURRENT)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEditing(false)
    setViewVersion(CURRENT)
    setError(null)
  }, [docId])

  const versions = useMemo(
    () => [...(versionsQuery.data ?? [])].sort((a, b) => b.version - a.version),
    [versionsQuery.data]
  )

  const versionOptions = useMemo(
    () => [
      { value: CURRENT, label: `当前版本 v${docQuery.data?.currentVersion ?? ''}` },
      ...versions.map((item) => ({
        value: String(item.version),
        label: `v${item.version} · ${item.snapshotReason || '历史版本'}`,
      })),
    ],
    [versions, docQuery.data?.currentVersion]
  )

  const doc = docQuery.data
  if (docQuery.isLoading) {
    return (
      <p className='text-muted-foreground flex items-center gap-2 p-4 text-sm'>
        <Spinner className='size-4' /> 正在加载文档…
      </p>
    )
  }
  if (docQuery.isError || !doc) {
    return <p className='text-destructive p-4 text-sm'>文档加载失败或不存在</p>
  }

  const isPlainFile = doc.sourceFormat === 'html' || doc.sourceFormat === 'pptx'
  const canEdit = hasPermission('report:studio:edit') && !isPlainFile
  const canRestore = hasPermission('report:studio:undo')

  const isHistoric =
    viewVersion !== CURRENT && Number(viewVersion) !== doc.currentVersion
  const historicVersion = isHistoric
    ? versions.find((item) => String(item.version) === viewVersion)
    : undefined

  const startEdit = () => {
    setDraft(doc.markdownContent)
    setEditing(true)
    setError(null)
  }

  const save = async () => {
    setError(null)
    try {
      await update.mutateAsync({
        docId: doc.docId,
        expectedVersion: doc.currentVersion,
        markdownContent: draft,
      })
      setEditing(false)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : '保存失败（版本可能已变化，请重新打开）'
      )
    }
  }

  /** 恢复历史版本：后端按该版本正文生成新版本（不覆盖版本链） */
  const restoreVersion = async () => {
    if (!historicVersion) return
    setError(null)
    try {
      await restore.mutateAsync({
        docId: doc.docId,
        version: historicVersion.version,
        expectedVersion: doc.currentVersion,
      })
      setViewVersion(CURRENT)
    } catch (err) {
      setError(err instanceof Error ? err.message : '恢复版本失败，请重新打开文档')
    }
  }

  const body = isHistoric
    ? (historicVersion?.markdownContent ?? '')
    : editing
      ? draft
      : doc.markdownContent

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <Badge variant='outline'>{STUDIO_SOURCE_TYPE_LABEL[doc.sourceType]}</Badge>
        <Badge variant='secondary'>版本 {doc.currentVersion}</Badge>
        {doc.reportId !== null && (
          <span className='text-muted-foreground text-xs'>关联报告 #{doc.reportId}</span>
        )}
        {doc.sourceFormat && (
          <span className='text-muted-foreground text-xs'>
            {doc.sourceFormat.toUpperCase()} · {formatSize(doc.sourceFileSize)}
          </span>
        )}
        <span className='text-muted-foreground inline-flex items-center gap-1 text-xs'>
          <History className='size-3' />
          {versions.length} 个历史版本
        </span>
        {versions.length > 0 && !isPlainFile && (
          <Select
            items={versionOptions}
            value={viewVersion}
            onValueChange={(value) => setViewVersion(value ?? CURRENT)}
          >
            <SelectTrigger aria-label='切换文档版本' className='h-7 w-36 text-xs'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {versionOptions.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <div className='ml-auto flex items-center gap-2'>
          {isHistoric && canRestore && (
            <Button
              size='sm'
              variant='outline'
              disabled={restore.isPending}
              onClick={() => void restoreVersion()}
            >
              <History data-icon='inline-start' />
              {restore.isPending ? '恢复中…' : `恢复 v${historicVersion?.version ?? ''}`}
            </Button>
          )}
          {!editing && canEdit && !isPlainFile && !isHistoric && (
            <Button size='sm' variant='outline' onClick={startEdit}>
              <Pencil data-icon='inline-start' /> 编辑
            </Button>
          )}
          {editing && (
            <>
              <Button size='sm' variant='ghost' onClick={() => setEditing(false)}>
                取消
              </Button>
              <Button size='sm' disabled={update.isPending} onClick={() => void save()}>
                <Save data-icon='inline-start' />
                {update.isPending ? '保存中…' : '保存'}
              </Button>
            </>
          )}
        </div>
      </div>

      {isHistoric && (
        <p className='text-muted-foreground text-xs'>
          正在查看历史版本 v{historicVersion?.version ?? ''}（只读）；
          {compactDate(historicVersion?.createdAt ?? null)} 保存 ·
          {historicVersion?.snapshotReason || '历史版本'}
        </p>
      )}

      {error && <p className='text-destructive text-sm'>{error}</p>}

      {needsChartRebind(doc) && (
        <div className='border-destructive/40 bg-destructive/5 text-destructive rounded-md border px-3 py-2 text-sm'>
          该文档的 {doc.chartRefs.length} 个图表没有可用的平台报告（搬运时源报告缺失），
          图表区显示「需重新绑定报告」，正文不受影响。
        </div>
      )}

      <div className='min-h-0 flex-1 overflow-y-auto rounded-md border p-4'>
        {isPlainFile ? (
          <SourceFilePreview doc={doc} />
        ) : editing ? (
          <Textarea
            className='min-h-[360px] font-mono text-xs'
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        ) : body ? (
          <Markdown>{body}</Markdown>
        ) : (
          <p className='text-muted-foreground text-sm'>文档正文为空</p>
        )}
      </div>
    </div>
  )
}

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
                      <button
                        className={`hover:bg-muted/60 w-full px-3 py-2 text-left ${
                          activeDocId === doc.docId ? 'bg-muted' : ''
                        }`}
                        type='button'
                        onClick={() => setActiveDocId(doc.docId)}
                      >
                        <span className='flex items-center gap-1.5'>
                          <FileText className='text-muted-foreground size-3.5 shrink-0' />
                          <span className='min-w-0 truncate text-sm'>{doc.title || doc.docId}</span>
                        </span>
                        <span className='mt-1 flex items-center gap-1.5'>
                          <Badge variant='outline'>
                            {STUDIO_SOURCE_TYPE_LABEL[doc.sourceType]}
                          </Badge>
                          <span className='text-muted-foreground text-[11px]'>
                            v{doc.currentVersion} · {compactDate(doc.updatedAt ?? doc.createdAt)}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className='flex min-h-0 min-w-0 flex-1 flex-col'>
              {activeDocId ? (
                <DocumentDetail docId={activeDocId} />
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
