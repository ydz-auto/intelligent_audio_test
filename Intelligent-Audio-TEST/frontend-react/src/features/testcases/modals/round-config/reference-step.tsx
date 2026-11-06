/**
 * 轮次步骤⑤：参考参数（11_用例域.md §5.1）。
 * 路径行（FolderOpen 图标 + 后端真实 referenceParamsPath）+「查看/编辑」切换钮；
 * 未生成时空态「参考参数将在音频关联后自动生成」；编辑态 Textarea mono + 「保存」（进行中「保存中…」）。
 * INT-1642 接线：内容与路径来自 GET /testcases/{id}/rounds/{n}/ref-params（真实文件），
 * 保存走 PUT 同端点（task_service 写回 referenceParamsPath 指向的 JSON 文件），不再本地 state 假装保存。
 * 后端端点当前只认 config.rounds[].referenceParamsPath（保存侧已剥离该键，见 FEAT INT-1645），
 * 故路径行以用例 reference_params 独立列兜底：无路径 → 「未生成」空态；有路径但内容读不到 →
 * 展示真实路径 + 显式失败态（不伪装成未生成）。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Pencil, RefreshCw, Save } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  fetchRoundRefParams,
  updateRoundRefParams,
} from '@/infrastructure/api/testcases-api'

/** 参考参数文件读写 query key（保存后回写缓存，切步骤再回来即最新内容） */
export function roundRefParamsQueryKey(caseId: string, roundNumber: number) {
  return ['testcase-ref-params', caseId, roundNumber] as const
}

/** 后端「未生成参考参数 / 路径缺失 / 用例不存在」统一回业务码 404（HTTP 400 + code 404） */
function isRefParamsMissing(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  return Number(error.code) === 404 || error.httpStatus === 404
}

/**
 * 用例独立列 reference_params（[{round_number, reference_params_path}]）→ 指定轮真实路径。
 * 读接口按 config.rounds[].referenceParamsPath 取路径，而保存侧会剥掉该键（路径只落在独立列），
 * 故路径行以列表/详情已带回的独立列为准兜底；内容仍走 GET .../ref-params（后端缺陷待 FEAT 修复）。
 */
export function referencePathForRound(
  referenceParams: unknown,
  roundNumber: number
): string | null {
  if (!Array.isArray(referenceParams)) return null
  for (const entry of referenceParams) {
    if (typeof entry !== 'object' || entry === null) continue
    const rec = entry as Record<string, unknown>
    const rn = Number(rec.round_number ?? rec.roundNumber)
    if (rn !== roundNumber) continue
    const path = rec.reference_params_path ?? rec.referenceParamsPath
    if (typeof path === 'string' && path) return path
  }
  return null
}

export function ReferenceStep({
  caseId,
  roundNumber,
  generated = false,
  pathFallback = null,
}: {
  /** 当前用例 id（新建未保存时为 null：无参考参数可读） */
  caseId?: string | null
  /** 当前轮次号（config.rounds[].roundNumber） */
  roundNumber: number
  /** 该轮已关联音频（无音频时后端不会生成参考参数，直接空态，省一次请求） */
  generated?: boolean
  /** 该轮参考参数文件路径（用例 reference_params 独立列回退；内容接口取不到时仍展示真实路径） */
  pathFallback?: string | null
}) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const enabled = Boolean(caseId) && generated
  const refQuery = useQuery({
    queryKey: roundRefParamsQueryKey(caseId ?? '', roundNumber),
    queryFn: () => fetchRoundRefParams(caseId as string, roundNumber),
    enabled,
    retry: false,
  })

  const missing = isRefParamsMissing(refQuery.error)
  // 独立列带回的真实路径：内容接口取不到时仍展示路径（不再出现假路径）
  const path = refQuery.data?.referenceParamsPath || pathFallback || ''
  const showEmpty = !enabled || (missing && !path)

  const startEdit = async () => {
    // 进入编辑前确保拿到最新内容（切步骤回来不重取，靠缓存）
    const result = refQuery.data ?? (await refQuery.refetch()).data
    if (!result) return
    setDraft(JSON.stringify(result.referenceParams ?? {}, null, 2))
    setMode('edit')
  }

  const handleSave = async () => {
    if (!caseId) return
    let parsed: unknown
    try {
      parsed = JSON.parse(draft)
    } catch {
      toast.error('参考参数保存失败：内容不是合法 JSON')
      return
    }
    setSaving(true)
    try {
      const saved = await updateRoundRefParams(caseId, roundNumber, parsed)
      queryClient.setQueryData(roundRefParamsQueryKey(caseId, roundNumber), saved)
      toast.success('参考参数已保存')
      setMode('view')
    } catch (error) {
      toast.error(
        `参考参数保存失败：${
          error instanceof Error ? error.message : '请稍后重试'
        }`
      )
    } finally {
      setSaving(false)
    }
  }

  if (showEmpty) {
    return (
      <div className='flex items-center gap-3 rounded-lg border border-dashed p-4'>
        <FolderOpen aria-hidden='true' className='text-muted-foreground size-5 shrink-0' />
        <p className='text-muted-foreground text-sm'>
          参考参数将在音频关联后自动生成——当前轮次尚未生成参考参数。
        </p>
      </div>
    )
  }

  if (refQuery.isLoading) {
    return (
      <div className='text-muted-foreground flex items-center gap-2 rounded-lg border border-dashed p-4 text-sm'>
        <Spinner className='size-4' />
        加载参考参数...
      </div>
    )
  }

  // 路径存在但内容读不到（后端读接口只认 config.rounds[].referenceParamsPath，保存侧会剥离该键）：
  // 展示真实路径 + 显式失败原因，不伪装成「未生成」；修复见 FEAT 卡
  if (missing) {
    return (
      <div className='space-y-3'>
        <div className='bg-background ring-foreground/10 flex items-center gap-3 rounded-lg p-3 ring-1'>
          <FolderOpen aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
          <code className='text-muted-foreground min-w-0 flex-1 truncate text-xs' title={path}>
            {path}
          </code>
        </div>
        <div className='border-destructive/30 space-y-2 rounded-lg border p-4'>
          <p className='text-destructive text-sm'>
            参考参数内容读取失败：
            {refQuery.error instanceof Error ? refQuery.error.message : '请稍后重试'}
          </p>
          <Button
            type='button'
            variant='outline'
            size='sm'
            className='h-7 gap-1'
            onClick={() => void refQuery.refetch()}
          >
            <RefreshCw aria-hidden='true' className='size-3.5' />
            重试
          </Button>
        </div>
      </div>
    )
  }

  // 非 404 的失败（网络/权限/后端异常）：显式错误态 + 重试，不伪装成「未生成」
  if (refQuery.isError) {
    return (
      <div className='border-destructive/30 space-y-2 rounded-lg border p-4'>
        <p className='text-destructive text-sm'>
          参考参数加载失败：
          {refQuery.error instanceof Error ? refQuery.error.message : '请稍后重试'}
        </p>
        <Button
          type='button'
          variant='outline'
          size='sm'
          className='h-7 gap-1'
          onClick={() => void refQuery.refetch()}
        >
          <RefreshCw aria-hidden='true' className='size-3.5' />
          重试
        </Button>
      </div>
    )
  }

  const displayPath = path || '—'

  return (
    <div className='space-y-3'>
      <div className='bg-background ring-foreground/10 flex items-center gap-3 rounded-lg p-3 ring-1'>
        <FolderOpen aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
        <code
          className='text-muted-foreground min-w-0 flex-1 truncate text-xs'
          title={displayPath}
        >
          {displayPath}
        </code>
        <Button
          type='button'
          variant='ghost'
          size='sm'
          className='h-7 gap-1'
          onClick={() => {
            if (mode === 'view') void startEdit()
            else setMode('view')
          }}
        >
          {mode === 'view' ? (
            <>
              <Pencil aria-hidden='true' className='size-3.5' />
              查看/编辑
            </>
          ) : (
            <>
              <FolderOpen aria-hidden='true' className='size-3.5' />
              返回查看
            </>
          )}
        </Button>
      </div>
      {mode === 'edit' && (
        <div className='space-y-2'>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={5}
            className='font-mono text-xs'
            placeholder='编辑参考参数 JSON…'
            disabled={saving}
          />
          <div className='flex justify-end gap-2'>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='h-7'
              disabled={saving}
              onClick={() => setMode('view')}
            >
              取消
            </Button>
            <Button
              type='button'
              size='sm'
              className='h-7 gap-1'
              disabled={saving}
              onClick={() => void handleSave()}
            >
              {saving ? (
                <>
                  <Spinner className='size-3.5' />
                  保存中…
                </>
              ) : (
                <>
                  <Save aria-hidden='true' className='size-3.5' />
                  保存
                </>
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
