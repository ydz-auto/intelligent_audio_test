/**
 * 音频批量操作弹窗（§6.25；Dialog sm:max-w-2xl，标题随操作切换）。
 * 批量操作类型=移动/复制/删除/重命名（删除已由浮条 batch-action delete 承载）；
 * 移动/复制需选「目标位置：选择目标文件夹」；重命名=统一规则（前缀+序号/正则替换预览）；
 * 批量修改属性=元数据/音频类型/SPL值等（音频导入功能设计文档.md:482-489）。
 * 注意：后端 batch-action 白名单当前仅 delete/export/tags（audio_command_handler
 * handle_batch_action），move/copy/rename/modify-properties 返回「不支持的操作」——
 * 本卡标记 **待 FEAT**（后端扩展），UI 保留但禁用主钮并提示缺口。
 */
import { FolderTree } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Info } from 'lucide-react'
import {
  FOLDER_TARGET_OPTIONS,
  MODIFY_PROPERTY_OPTIONS,
} from '@/features/audio-import/constants'
import { useAudioMutations } from '@/application/audio/useAudioList'
import type { AudioBulkDialogState } from '@/features/audio-import/types'

export type AudioBatchOperationDialogProps = {
  state: AudioBulkDialogState | null
  onOpenChange: (open: boolean) => void
  count: number
  /** 已选中的音频 id（批量浮条「更多批量操作」触发时传入） */
  ids: number[]
}

const BULK_KINDS = ['move', 'copy', 'rename', 'modify-properties'] as const
type BulkKind = (typeof BULK_KINDS)[number]

/** 后端 batch-action 暂不支持的操作（待 FEAT；audio_command_handler 白名单仅 delete/export/tags） */
const UNSAFE_BACKEND_KINDS: ReadonlySet<BulkKind> = new Set([
  'move',
  'copy',
  'rename',
  'modify-properties',
])

const TITLES: Record<BulkKind, string> = {
  move: '批量移动音频',
  copy: '批量复制音频',
  rename: '批量重命名',
  'modify-properties': '批量修改属性',
}

const DESCRIPTIONS: Record<BulkKind, string> = {
  move: '将选中的音频移动到目标文件夹',
  copy: '将选中的音频复制到目标文件夹',
  rename: '按统一规则批量重命名选中的音频',
  'modify-properties': '批量修改选中音频的属性',
}

export function AudioBatchOperationDialog(props: AudioBatchOperationDialogProps) {
  const { batch } = useAudioMutations()
  const [targetFolder, setTargetFolder] = useState('test_data/dry')
  const [renameRule, setRenameRule] = useState('测试音频_')
  const [property, setProperty] = useState('metadata')
  const [pending, setPending] = useState(false)

  const kind = props.state?.kind ?? null
  const bulkKind: BulkKind | null =
    kind === 'move' || kind === 'copy' || kind === 'rename' || kind === 'modify-properties'
      ? kind
      : null

  const handleConfirm = async () => {
    if (!bulkKind) return
    setPending(true)
    try {
      const result = await batch.mutateAsync({ action: bulkKind, ids: props.ids })
      toast.success(
        `批量操作完成：成功 ${result.successCount} 失败 ${result.total - result.successCount}`
      )
      props.onOpenChange(false)
    } catch {
      toast.error('批量操作失败，请重试')
    } finally {
      setPending(false)
    }
  }

  const showFolderTarget = bulkKind === 'move' || bulkKind === 'copy'
  const showRenameRule = bulkKind === 'rename'
  const showProperty = bulkKind === 'modify-properties'

  return (
    <Dialog
      open={props.state != null}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) setPending(false)
      }}
    >
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{bulkKind ? TITLES[bulkKind] : '批量操作'}</DialogTitle>
          <DialogDescription>
            {bulkKind ? DESCRIPTIONS[bulkKind] : ''}（已选 {props.count} 个音频）
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {bulkKind && UNSAFE_BACKEND_KINDS.has(bulkKind) && (
            <Alert className='py-2'>
              <Info aria-hidden='true' className='size-4' />
              <AlertTitle className='text-sm font-medium'>后端待支持</AlertTitle>
              <AlertDescription>
                批量{bulkKind === 'move' ? '移动' : bulkKind === 'copy' ? '复制' : bulkKind === 'rename' ? '重命名' : '修改属性'}
                的后端接口尚未实现（batch-action 白名单仅 delete/export/tags），已开【FEAT】卡补齐，合入前暂不可用。
              </AlertDescription>
            </Alert>
          )}

          {showFolderTarget && (
            <div className='space-y-2'>
              <Label htmlFor='batch-folder-target'>目标位置：选择目标文件夹</Label>
              <Select
                value={targetFolder}
                onValueChange={(value) => setTargetFolder(value ?? 'test_data/dry')}
              >
                <SelectTrigger id='batch-folder-target' size='sm' className='w-full'>
                  <SelectValue placeholder='选择目标文件夹'>
                    {FOLDER_TARGET_OPTIONS.find((o) => o.value === targetFolder)?.label ?? ''}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {FOLDER_TARGET_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className='text-muted-foreground flex items-center gap-1.5 text-xs'>
                <FolderTree aria-hidden='true' className='size-3.5' />
                无权限的目标文件夹将禁用并提示
              </div>
            </div>
          )}

          {showRenameRule && (
            <div className='space-y-3'>
              <div className='space-y-2'>
                <Label htmlFor='batch-rename-rule'>统一命名规则</Label>
                <Input
                  id='batch-rename-rule'
                  value={renameRule}
                  onChange={(e) => setRenameRule(e.target.value)}
                  placeholder='前缀 + 序号，如 测试音频_'
                />
              </div>
              <div className='bg-muted/30 rounded-lg border p-3'>
                <div className='text-muted-foreground mb-1.5 text-xs font-medium'>
                  预览
                </div>
                <div className='space-y-1 font-mono text-xs'>
                  <p className='text-muted-foreground'>
                    客厅_中文_命令集.wav → <span className='text-foreground'>{renameRule}01.wav</span>
                  </p>
                  <p className='text-muted-foreground'>
                    车内_导航_1人.wav → <span className='text-foreground'>{renameRule}02.wav</span>
                  </p>
                </div>
              </div>
            </div>
          )}

          {showProperty && (
            <div className='space-y-2'>
              <Label htmlFor='batch-property'>修改属性</Label>
              <Select
                value={property}
                onValueChange={(value) => setProperty(value ?? 'metadata')}
              >
                <SelectTrigger id='batch-property' size='sm' className='w-full'>
                  <SelectValue placeholder='修改属性'>
                    {MODIFY_PROPERTY_OPTIONS.find((o) => o.value === property)?.label ?? ''}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {MODIFY_PROPERTY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {property === 'metadata' && (
                <p className='text-muted-foreground text-xs'>
                  批量修改元数据字段（描述/源语言/ASR 文本等）
                </p>
              )}
              {property === 'audio-type' && (
                <p className='text-muted-foreground text-xs'>
                  批量修改音频类型（干声/噪声/提示词音频/混合音频）
                </p>
              )}
              {property === 'spl' && (
                <p className='text-muted-foreground text-xs'>
                  批量设置默认声压级（SPL 值，30-120 dB）
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button
            size='sm'
            disabled={pending || (bulkKind != null && UNSAFE_BACKEND_KINDS.has(bulkKind))}
            onClick={handleConfirm}
          >
            {pending ? '执行中...' : '确认执行'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
