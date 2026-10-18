/**
 * 冻结任务详情弹窗（09_任务域.md §5.13，Dialog sm:max-w-3xl）。
 * 标题「任务详情（发布时冻结 · 不可变）」；三 DetailSection：
 * ①任务信息（名称/说明/算法类型/标签键值行）②关联资源（发布时冻结）
 * （被测设备/API/播放设备引用行）③用例（{n}）（每用例 Collapsible：
 * 名称+类型徽章+轮次+标签+分组，展开显描述+配置/算法参数 JSON 块+参考参数摘要块）。
 * 空态「冻结体无用例数据」；数据源 = PublishedTaskDetail.snapshot_config.taskSnapshot。
 */
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { TaskSnapshot, TaskSnapshotCase } from '@/domain/models/task'

const DEVICE_TYPE_LABELS: Record<string, string> = {
  physical: 'E2E',
  http_api: 'API',
  websocket_api: 'API(WS)',
}

function deviceTypeLabel(dt: string | null | undefined): string {
  return (dt && DEVICE_TYPE_LABELS[dt]) || dt || ''
}

/** 用例轮次数（config.rounds 数组长度；无则隐藏） */
function roundCount(c: TaskSnapshotCase): number {
  const rounds = c.config?.rounds
  return Array.isArray(rounds) ? rounds.length : 0
}

function prettyJson(val: unknown): string {
  try {
    return JSON.stringify(val, null, 2) ?? '—'
  } catch {
    return String(val)
  }
}

/** 参考参数渲染压缩：逐轮只显示条数与前两条示例（全量数据大，弹窗内不整屏铺开） */
function compactRefParams(list: TaskSnapshotCase['referenceParams']) {
  return (list ?? []).map((r) => ({
    roundNumber: r.roundNumber,
    itemCount: r.referenceParams?.length ?? 0,
    sample: (r.referenceParams ?? []).slice(0, 2),
  }))
}

/** DetailSection 分节（§5.13 三节：任务信息/关联资源/用例） */
function DetailSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className='rounded-lg border p-3'>
      <p className='text-sm font-medium'>{title}</p>
      <div className='mt-2'>{children}</div>
    </section>
  )
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='grid grid-cols-[100px_1fr] gap-2 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='min-w-0 break-words'>{value ?? '—'}</span>
    </div>
  )
}

function CaseItem({ c }: { c: TaskSnapshotCase }) {
  const [open, setOpen] = useState(false)
  const rounds = roundCount(c)
  const refParams = compactRefParams(c.referenceParams)
  const hasRefParams = (c.referenceParams?.length ?? 0) > 0

  return (
    <Collapsible open={open} onOpenChange={setOpen} className='rounded-lg border'>
      <CollapsibleTrigger
        render={
          <button
            type='button'
            className='flex w-full flex-wrap items-center gap-1.5 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/40'
          >
            <span className='font-medium'>{c.name || c.caseId}</span>
            {c.algorithmType && (
              <Badge variant='secondary' className='rounded-md px-1.5 text-[11px]'>
                {c.algorithmType}
              </Badge>
            )}
            {deviceTypeLabel(c.deviceType) && (
              <Badge variant='outline' className='rounded-md px-1.5 text-[11px]'>
                {deviceTypeLabel(c.deviceType)}
              </Badge>
            )}
            {rounds > 0 && (
              <span className='text-muted-foreground text-xs'>{rounds} 轮</span>
            )}
            {(c.tags ?? []).length > 0 && (
              <span className='text-muted-foreground text-xs'>
                {(c.tags ?? []).join('、')}
              </span>
            )}
            {c.group?.name && (
              <span className='text-muted-foreground text-xs'>{c.group.name}</span>
            )}
          </button>
        }
      />
      <CollapsibleContent className='border-t px-3 py-2.5'>
        <div className='flex flex-col gap-2'>
          {c.description && <FieldRow label='描述' value={c.description} />}
          <div className='rounded-md bg-muted/40 p-3 font-mono text-xs'>
            {prettyJson(c.config ?? {})}
          </div>
          {c.algorithmParams && Object.keys(c.algorithmParams).length > 0 && (
            <div>
              <p className='text-muted-foreground mb-1 text-xs'>算法参数</p>
              <div className='rounded-md bg-muted/40 p-3 font-mono text-xs'>
                {prettyJson(c.algorithmParams)}
              </div>
            </div>
          )}
          {hasRefParams && (
            <div>
              <p className='text-muted-foreground mb-1 text-xs'>
                参考参数（内容内联 · {(c.referenceParams ?? []).length} 轮）
              </p>
              <div className='rounded-md bg-muted/40 p-3 font-mono text-xs'>
                {prettyJson(refParams)}
              </div>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

export function TaskSnapshotDialog({
  open,
  onOpenChange,
  snapshot,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 冻结体（source = PublishedTaskDetail.snapshot_config.taskSnapshot；null → 不渲染） */
  snapshot: TaskSnapshot | null
}) {
  const cases = useMemo(() => snapshot?.cases ?? [], [snapshot])
  const taskInfo = snapshot?.task
  const refsRows = useMemo(() => {
    if (!snapshot) return []
    const rows: { kind: string; text: string }[] = []
    const fmt = (list: TaskSnapshot['devices']) =>
      (list ?? []).map((r) => (r.name ? `${r.name} (#${r.id})` : `#${r.id}`)).join('、')
    const devices = fmt(snapshot.devices)
    const apis = fmt(snapshot.apis)
    const playbacks = fmt(snapshot.playbackDevices)
    if (devices) rows.push({ kind: '被测设备', text: devices })
    if (apis) rows.push({ kind: 'API', text: apis })
    if (playbacks) rows.push({ kind: '播放设备', text: playbacks })
    return rows
  }, [snapshot])

  if (!snapshot) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>任务详情（发布时冻结 · 不可变）</DialogTitle>
          <DialogDescription>快照数据不随源任务/源用例改动变化</DialogDescription>
        </DialogHeader>

        <ScrollArea className='max-h-[min(72dvh,720px)] pr-1'>
          <div className='flex flex-col gap-3'>
            <DetailSection title='任务信息'>
              <div className='grid gap-1.5 sm:grid-cols-2'>
                <FieldRow label='名称' value={taskInfo?.name} />
                <FieldRow label='算法类型' value={taskInfo?.algorithmType} />
                {taskInfo?.description && (
                  <div className='sm:col-span-2'>
                    <FieldRow label='说明' value={taskInfo.description} />
                  </div>
                )}
                {(taskInfo?.tags ?? []).length > 0 && (
                  <div className='sm:col-span-2'>
                    <FieldRow label='标签' value={(taskInfo?.tags ?? []).join('、')} />
                  </div>
                )}
              </div>
            </DetailSection>

            {refsRows.length > 0 && (
              <DetailSection title='关联资源（发布时冻结）'>
                <div className='flex flex-col gap-1.5'>
                  {refsRows.map((row) => (
                    <FieldRow key={row.kind} label={row.kind} value={row.text} />
                  ))}
                </div>
              </DetailSection>
            )}

            <DetailSection title={`用例（${cases.length}）`}>
              {cases.length === 0 ? (
                <p className='text-muted-foreground rounded-md border border-dashed bg-muted/30 px-4 py-6 text-center text-sm'>
                  冻结体无用例数据
                </p>
              ) : (
                <div className='flex flex-col gap-1.5'>
                  {cases.map((c) => (
                    <CaseItem key={c.caseId} c={c} />
                  ))}
                </div>
              )}
            </DetailSection>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
