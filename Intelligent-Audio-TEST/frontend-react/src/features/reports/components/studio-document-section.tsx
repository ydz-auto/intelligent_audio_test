/**
 * Studio 文档区（INT-1766 D8 返工）：可嵌入页面的文档列表 + 正文查看器。
 *
 * 从哪里进来（三处共用一套取数口径）：
 * - 报告中心「更多操作 → 报告文档」：`StudioDocumentLibraryDialog`，不限定 report_id，
 *   按 `source_type` 筛选（全部 / 上传文档 / Agent 总结 / 平台报告文档）；
 * - 报告详情页 `/report/$reportId`：固定 `report_id=<当前报告>` +
 *   `source_type=platform_report`（后端 report_studio_bp.list_documents 契约：平台报告详情页
 *   只列平台报告文档，不混入上传文档）；
 * - 任务详情页 `/tasks/$id`：先按 `task_id` 取该任务的报告 id，再按 `report_id` 列出全部关联
 *   文档（上传时给了 task_id 的独立报告后端落成该报告的 report_id）。
 *
 * 打开文档的行为与文档库一致：md 可读可编辑（PUT 乐观锁），html/pptx 走鉴权 Blob 预览/下载，
 * `chart_refs` 非空且 `report_id` 为空时图表区提示「需重新绑定报告」，正文照常渲染。
 */
import { Download, FileText, History, Pencil, Save } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Markdown } from '@/components/ui/markdown'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
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
  needsChartRebind,
  type StudioDocument,
  type StudioSourceTypeValue,
} from '@/domain/models/report-studio'
import { fetchStudioSourceBlob } from '@/infrastructure/api/reportStudioApi'
import { cn } from '@/lib/utils'
import { formatDateTime } from '@/lib/date-time'

/** 版本下拉的「当前版本」哨兵值（Select 不接受空字符串 as value） */
export const CURRENT_VERSION = '__current__'

export function formatSize(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function compactDate(value: string | null): string {
  // 后端时间串为裸 UTC，统一走共享口径转本地时区（INT-2211）
  return formatDateTime(value)
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

/** 单文档正文区（列表选中后渲染；报告详情页 / 任务详情 / 文档库三处共用） */
export function StudioDocumentDetail({ docId }: { docId: string }) {
  const { hasPermission } = usePermissions()
  const docQuery = useStudioDocument(docId)
  const versionsQuery = useStudioDocumentVersions(docId)
  const update = useUpdateStudioDocument()
  const restore = useRestoreStudioDocumentVersion()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [viewVersion, setViewVersion] = useState<string>(CURRENT_VERSION)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEditing(false)
    setViewVersion(CURRENT_VERSION)
    setError(null)
  }, [docId])

  const versions = useMemo(
    () => [...(versionsQuery.data ?? [])].sort((a, b) => b.version - a.version),
    [versionsQuery.data]
  )

  const versionOptions = useMemo(
    () => [
      { value: CURRENT_VERSION, label: `当前版本 v${docQuery.data?.currentVersion ?? ''}` },
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
    viewVersion !== CURRENT_VERSION && Number(viewVersion) !== doc.currentVersion
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
      setViewVersion(CURRENT_VERSION)
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
            onValueChange={(value) => setViewVersion(value ?? CURRENT_VERSION)}
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

/** 文档列表行（列表项 + 来源徽章 + 版本/时间） */
export function StudioDocumentRow({
  doc,
  active,
  onClick,
}: {
  doc: StudioDocument
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      className={cn('hover:bg-muted/60 w-full px-3 py-2 text-left', active && 'bg-muted')}
      type='button'
      onClick={onClick}
    >
      <span className='flex items-center gap-1.5'>
        <FileText className='text-muted-foreground size-3.5 shrink-0' />
        <span className='min-w-0 truncate text-sm'>{doc.title || doc.docId}</span>
      </span>
      <span className='mt-1 flex items-center gap-1.5'>
        <Badge className='shrink-0 whitespace-nowrap' variant='outline'>
          {STUDIO_SOURCE_TYPE_LABEL[doc.sourceType]}
        </Badge>
        <span className='text-muted-foreground min-w-0 truncate text-[11px]'>
          v{doc.currentVersion} · {compactDate(doc.updatedAt ?? doc.createdAt)}
        </span>
      </span>
    </button>
  )
}

export interface StudioDocumentSectionProps {
  title: string
  /** 区块副标题（说明取数口径，避免用户误解列表范围） */
  description?: string
  /** 文档所属报告；取数固定带 `report_id` */
  reportId: number
  /** 来源过滤；不传即该报告下的全部来源 */
  sourceType?: StudioSourceTypeValue
  emptyText?: string
  className?: string
}

/**
 * 嵌入式文档区：左侧列表 + 右侧正文，数据按 `reportId`（+ `sourceType`）取，
 * 默认选中第一份，打开页面即可看到正文。
 */
export function StudioDocumentSection({
  title,
  description,
  reportId,
  sourceType,
  emptyText = '暂无文档',
  className,
}: StudioDocumentSectionProps) {
  const [activeDocId, setActiveDocId] = useState<string | null>(null)

  const query = useMemo(
    () => ({ reportId, sourceType, limit: 100 }),
    [reportId, sourceType]
  )
  const listQuery = useStudioDocuments(query, { enabled: Number.isFinite(reportId) })
  const items = listQuery.data?.items

  // 数据到达/刷新后默认选中第一份；已选中的文档仍在列表里则保持（避免编辑中被重置）
  useEffect(() => {
    const list = items ?? []
    setActiveDocId((prev) =>
      prev && list.some((doc) => doc.docId === prev) ? prev : (list[0]?.docId ?? null)
    )
  }, [items])

  const isEmpty =
    !listQuery.isLoading && !listQuery.isError && (items?.length ?? 0) === 0

  return (
    <section
      aria-label={title}
      className={cn('bg-card rounded-2xl border p-4 shadow-xs sm:p-5', className)}
    >
      <div className='flex flex-wrap items-center gap-2'>
        <h3 className='text-sm font-semibold'>{title}</h3>
        <Badge variant='secondary' className='rounded-md px-1.5 text-[11px] tabular-nums'>
          {listQuery.data?.total ?? 0} 份
        </Badge>
      </div>
      {description && <p className='text-muted-foreground mt-1 text-xs'>{description}</p>}

      {isEmpty ? (
        <p className='text-muted-foreground mt-3 rounded-md border border-dashed p-6 text-center text-sm'>
          {emptyText}
        </p>
      ) : (
        <div className='mt-3 grid gap-3 md:grid-cols-[220px_minmax(0,1fr)]'>
          <div className='max-h-[420px] overflow-y-auto rounded-md border'>
            {listQuery.isLoading ? (
              <p className='text-muted-foreground flex items-center gap-2 p-3 text-sm'>
                <Spinner className='size-4' /> 加载中…
              </p>
            ) : listQuery.isError ? (
              <p className='text-destructive p-3 text-sm'>文档列表加载失败</p>
            ) : (
              <ul className='divide-y'>
                {items?.map((doc) => (
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

          <div className='flex h-[460px] min-h-0 min-w-0 flex-col'>
            {activeDocId ? (
              <StudioDocumentDetail docId={activeDocId} />
            ) : (
              <p className='text-muted-foreground m-auto text-sm'>从左侧选择一份文档查看</p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
