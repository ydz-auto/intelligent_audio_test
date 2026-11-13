/**
 * 报告工作模式·文档面板（interfaces 层 ai-chat/studio；08_AI对话页.md §3.6，
 * 设计文档 §15.5 取数 → 起草 → 版本 → 导出）。
 *
 * 真实接线（INT-2473，全部经 infrastructure/api → client.ts）：
 * - 文档列表 / 详情：GET /report-studio/documents?report_id=&source_type=platform_report
 * - 起草：POST /report-studio/documents（绑定报告上下文生成 v1 草稿）
 * - 保存：PUT /documents/{id}（expected_version 乐观锁，前后端都按版本号校验）
 * - 版本：GET /documents/{id}/versions + POST /documents/{id}/restore（version-list）
 * - 导出：POST /documents/{id}/exports + GET /exports/{id} 轮询 + 下载（export-panel）
 *
 * 状态：无上下文 / 加载 / 空（未起草）/ 错误（可重试）/ 编辑中；底部来源卡显示
 * 报告 / 任务来源 ID，并展示当前 run 的写操作审批状态（与审批卡同一数据源）。
 */
import {
  Download,
  FileText,
  History,
  Loader2,
  PenLine,
  Plus,
  Save,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { Response } from '@/components/ai-elements/response'

import { usePermissions } from '@/application/hooks/use-permissions'
import {
  useCreateStudioDocument,
  useStudioDocument,
  useStudioDocuments,
  useUpdateStudioDocument,
} from '@/application/reports/use-report-studio'
import { StudioSourceType } from '@/domain/models/report-studio'
import { usePendingApprovals } from '@/features/ai-chat/hooks/use-pending-approvals'

import { ExportPanel } from './export-panel'
import { VersionList } from './version-list'

type DocumentPanelProps = {
  /** 绑定的平台报告 id（任务上下文先解析成报告 id 再传入；未绑定为 null） */
  reportId: number | null
  /** 上下文来源类型（来源卡显示「报告 #x」/「任务 #y」） */
  sourceKind: 'report' | 'task' | null
  sourceId: string | null
  sourceLabel?: string
  /** 当前平台 Agent 会话 id（AI 起草时随起草请求落库） */
  agentSessionId?: string | null
  /** 当前 run id（读待审批写操作数；空表示无在跑 run） */
  runId?: string | null
  onClose: () => void
}

/** 起草默认正文：只声明来源，不杜撰报告数值（红线：不编造数据） */
function buildDraftMarkdown(title: string, reportId: number): string {
  return [
    `# ${title}`,
    '',
    `> 数据来源：报告 #${reportId}（Studio 草稿，正文待 AI 起草或人工填写）`,
    '',
  ].join('\n')
}

export function DocumentPanel({
  reportId,
  sourceKind,
  sourceId,
  sourceLabel,
  agentSessionId,
  runId,
  onClose,
}: DocumentPanelProps) {
  const { hasPermission } = usePermissions()
  const canCreate = hasPermission('report:studio:create')
  const canEdit = hasPermission('report:studio:edit')
  const canUndo = hasPermission('report:studio:undo')
  const canExport = hasPermission('report:studio:export')

  const [activeDocId, setActiveDocId] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [versionOpen, setVersionOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  const docsQuery = useStudioDocuments(
    {
      reportId: reportId ?? undefined,
      sourceType: StudioSourceType.PLATFORM_REPORT,
      limit: 20,
    },
    { enabled: reportId !== null }
  )

  const documents = useMemo(() => {
    const items = [...(docsQuery.data?.items ?? [])]
    // 最新文档优先：updatedAt 缺失时按创建时间、再按版本号回退
    return items.sort((a, b) => {
      const left = a.updatedAt ?? a.createdAt ?? ''
      const right = b.updatedAt ?? b.createdAt ?? ''
      if (left !== right) return right.localeCompare(left)
      return b.currentVersion - a.currentVersion
    })
  }, [docsQuery.data])

  const activeSummary = documents.find((doc) => doc.docId === activeDocId) ?? documents[0]
  const docQuery = useStudioDocument(activeSummary?.docId ?? null)
  const doc = docQuery.data ?? null

  const createDraft = useCreateStudioDocument()
  const updateDoc = useUpdateStudioDocument()

  // 上下文切换 / 文档被删后回到最新文档
  useEffect(() => {
    setEditing(false)
    setSaveError(null)
  }, [reportId, activeSummary?.docId])

  const sourceTitle =
    sourceLabel?.trim() ||
    (sourceKind === 'task' ? `任务 #${sourceId}` : `报告 #${reportId}`)

  const handleCreateDraft = async () => {
    if (reportId === null) return
    const title = `${sourceTitle} 草稿`
    try {
      const created = await createDraft.mutateAsync({
        reportId,
        title,
        markdownContent: buildDraftMarkdown(title, reportId),
        agentSessionId: agentSessionId ?? null,
      })
      setActiveDocId(created.docId)
      setEditing(false)
      setSaveError(null)
    } catch {
      // 失败由 createDraft.error 展示
    }
  }

  const startEdit = () => {
    if (!doc) return
    setDraft(doc.markdownContent)
    setEditing(true)
    setSaveError(null)
  }

  const handleSave = async () => {
    if (!doc) return
    setSaveError(null)
    try {
      await updateDoc.mutateAsync({
        docId: doc.docId,
        expectedVersion: doc.currentVersion,
        markdownContent: draft,
      })
      setEditing(false)
    } catch (error) {
      setSaveError(
        error instanceof Error
          ? error.message
          : '保存失败（版本可能已变化，请刷新后重试）'
      )
    }
  }

  const { pendingCount, isLoading: approvalsLoading, isError: approvalsError } =
    usePendingApprovals(runId ?? null)

  const createError =
    createDraft.error instanceof Error ? createDraft.error.message : null
  const isPlainFile = doc?.sourceFormat === 'html' || doc?.sourceFormat === 'pptx'
  const canEditDoc = canEdit && doc !== null && !isPlainFile

  return (
    <div
      className='border-border/60 bg-background/60 dark:bg-background/40 flex min-h-0 flex-col border-l'
      data-testid='studio-document-panel'
    >
      {/* 头行：文档名 + 版本 + 历史版本 / 导出 / 编辑 / 关闭 */}
      <div className='border-b px-4 py-2.5'>
        <div className='flex items-center gap-2'>
          <FileText className='text-muted-foreground size-4 shrink-0' />
          <span className='min-w-0 truncate text-sm font-semibold'>
            {doc?.title ?? sourceTitle}
          </span>
          {doc && (
            <Badge className='shrink-0' variant='outline'>
              版本 {doc.currentVersion}
            </Badge>
          )}
          <div className='ml-auto flex items-center gap-0.5'>
            <Button
              aria-label='历史版本'
              className='text-muted-foreground size-7'
              disabled={!doc}
              onClick={() => setVersionOpen(true)}
              size='icon'
              title='历史版本'
              type='button'
              variant='ghost'
            >
              <History className='size-4' />
            </Button>
            <Button
              aria-label='导出'
              className='text-muted-foreground size-7'
              disabled={!doc}
              onClick={() => setExportOpen(true)}
              size='icon'
              title='导出'
              type='button'
              variant='ghost'
            >
              <Download className='size-4' />
            </Button>
            <Button
              aria-label={editing ? '取消编辑' : '编辑文档'}
              className='text-muted-foreground size-7'
              disabled={!canEditDoc}
              onClick={() => (editing ? setEditing(false) : startEdit())}
              size='icon'
              title={editing ? '取消编辑' : '编辑文档'}
              type='button'
              variant='ghost'
            >
              <PenLine className='size-4' />
            </Button>
            <Button
              aria-label='关闭'
              className='text-muted-foreground size-7'
              onClick={onClose}
              size='icon'
              title='关闭'
              type='button'
              variant='ghost'
            >
              <X className='size-4' />
            </Button>
          </div>
        </div>
      </div>

      {/* 正文区：加载 / 错误 / 空 / 预览 / 编辑 */}
      <div className='min-h-0 flex-1 overflow-y-auto px-5 py-4'>
        {reportId === null ? (
          <EmptyBlock
            description='先在输入框左侧绑定报告上下文，再打开报告工作模式。'
            title='未绑定报告上下文'
          />
        ) : docsQuery.isLoading ? (
          <LoadingBlock label='正在加载报告文档…' />
        ) : docsQuery.isError ? (
          <ErrorBlock
            message='文档列表加载失败'
            onRetry={() => void docsQuery.refetch()}
          />
        ) : documents.length === 0 ? (
          <div
            className='grid place-items-center gap-3 px-4 py-10 text-center'
            data-testid='studio-document-empty'
          >
            <FileText className='text-muted-foreground/60 size-8' />
            <div className='space-y-1'>
              <p className='text-sm font-medium'>该报告还没有 Studio 文档</p>
              <p className='text-muted-foreground text-xs'>
                起草后可在对话里让 AI 生成正文，或直接人工编辑。
              </p>
            </div>
            <Button
              className='gap-1.5'
              data-testid='studio-draft-button'
              disabled={!canCreate || createDraft.isPending}
              onClick={() => void handleCreateDraft()}
              size='sm'
              type='button'
            >
              {createDraft.isPending ? (
                <Loader2 className='size-4 animate-spin' />
              ) : (
                <Plus className='size-4' />
              )}
              起草文档
            </Button>
            {!canCreate && (
              <p className='text-muted-foreground text-xs'>
                缺少起草权限（report:studio:create）。
              </p>
            )}
            {createError && (
              <p className='text-destructive text-xs'>{createError}</p>
            )}
          </div>
        ) : docQuery.isLoading ? (
          <LoadingBlock label='正在加载文档正文…' />
        ) : docQuery.isError || !doc ? (
          <ErrorBlock
            message='文档正文加载失败或文档不存在'
            onRetry={() => void docQuery.refetch()}
          />
        ) : editing ? (
          <div className='grid gap-2'>
            <Textarea
              className='min-h-[18rem] resize-y font-mono text-[13px] leading-6'
              data-testid='studio-document-editor'
              onChange={(event) => setDraft(event.target.value)}
              spellCheck={false}
              value={draft}
            />
            <div className='flex items-center justify-end gap-2'>
              <Button
                disabled={updateDoc.isPending}
                onClick={() => setEditing(false)}
                size='sm'
                type='button'
                variant='ghost'
              >
                取消
              </Button>
              <Button
                className='gap-1.5'
                data-testid='studio-document-save'
                disabled={updateDoc.isPending || draft === doc.markdownContent}
                onClick={() => void handleSave()}
                size='sm'
                type='button'
              >
                {updateDoc.isPending ? (
                  <Loader2 className='size-4 animate-spin' />
                ) : (
                  <Save className='size-4' />
                )}
                保存并生成 v{doc.currentVersion + 1}
              </Button>
            </div>
            {saveError && (
              <p className='text-destructive text-xs'>{saveError}</p>
            )}
          </div>
        ) : (
          <div data-testid='studio-document-content'>
            {doc.markdownContent.trim() ? (
              <Response>{doc.markdownContent}</Response>
            ) : (
              <p className='text-muted-foreground text-sm'>
                文档暂无正文，点击右上角编辑按钮填写。
              </p>
            )}
          </div>
        )}
      </div>

      {/* 底部：写操作审批状态 + 来源卡（报告 / 任务上下文来源 ID） */}
      <div className='border-t px-4 py-2 text-xs text-muted-foreground'>
        <ApprovalStrip
          isLoading={approvalsLoading}
          isError={approvalsError}
          pendingCount={pendingCount}
          runId={runId ?? null}
        />
        <div
          className='mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5'
          data-testid='studio-source-card'
        >
          <span className='text-foreground/80 font-medium'>取数来源</span>
          <Badge className='font-normal' variant='secondary'>
            {sourceKind === 'task'
              ? `任务 #${sourceId ?? '—'}`
              : `报告 #${reportId ?? '—'}`}
          </Badge>
          {sourceKind === 'task' && reportId !== null && (
            <span className='text-[11px]'>→ 报告 #{reportId}</span>
          )}
          <span className='text-[11px]'>AI 只起草不算数：数值以报告七表为准</span>
        </div>
      </div>

      {doc && (
        <>
          <VersionList
            canRestore={canUndo}
            currentVersion={doc.currentVersion}
            docId={doc.docId}
            onOpenChange={setVersionOpen}
            open={versionOpen}
          />
          <ExportPanel
            canExport={canExport}
            docId={doc.docId}
            docTitle={doc.title}
            onOpenChange={setExportOpen}
            open={exportOpen}
            version={doc.currentVersion}
          />
        </>
      )}
    </div>
  )
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <p className='text-muted-foreground flex items-center gap-2 py-6 text-sm'>
      <Spinner className='size-4' />
      {label}
    </p>
  )
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className='flex items-center justify-between gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive'>
      <span>{message}</span>
      <Button onClick={onRetry} size='sm' type='button' variant='outline'>
        重试
      </Button>
    </div>
  )
}

function EmptyBlock({ title, description }: { title: string; description: string }) {
  return (
    <div className='grid place-items-center gap-2 px-4 py-12 text-center'>
      <FileText className='text-muted-foreground/60 size-8' />
      <p className='text-sm font-medium'>{title}</p>
      <p className='text-muted-foreground text-xs'>{description}</p>
    </div>
  )
}

/**
 * 写操作审批状态条：Agent 发起的生成 / 导出在批准前不执行，
 * 面板据此提示待审批数（与审批卡同一 /agent/runs/{id}/approvals 契约）。
 */
function ApprovalStrip({
  runId,
  pendingCount,
  isLoading,
  isError,
}: {
  runId: string | null
  pendingCount: number
  isLoading: boolean
  isError: boolean
}) {
  if (!runId) {
    return (
      <div data-testid='studio-approval-status'>
        审批：手动起草 / 编辑 / 导出按当前账号权限直写；Agent 代操作走审批卡。
      </div>
    )
  }
  if (isLoading) {
    return (
      <div className='flex items-center gap-1.5' data-testid='studio-approval-status'>
        <Loader2 className='size-3 animate-spin' />
        审批：读取中…
      </div>
    )
  }
  if (isError) {
    return (
      <div className='text-destructive' data-testid='studio-approval-status'>
        审批：状态读取失败（不影响手动编辑与导出）
      </div>
    )
  }
  if (pendingCount > 0) {
    return (
      <div
        className='rounded bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-400'
        data-testid='studio-approval-status'
      >
        审批：{pendingCount} 项写操作待审批，批准后才会生成 / 更新文档或导出
      </div>
    )
  }
  return (
    <div data-testid='studio-approval-status'>审批：当前 run 无待审批写操作</div>
  )
}
