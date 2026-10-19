/**
 * 音频批量操作弹窗（§6.25；Dialog sm:max-w-2xl，标题随操作切换）。
 * 批量操作类型=移动/复制/删除/重命名（删除已由浮条 batch-action delete 承载）；
 * 移动/复制需选「目标位置：选择目标文件夹」；重命名=统一规则（前缀+序号/正则替换预览）；
 * 批量修改属性=元数据/音频类型/SPL值等（音频导入功能设计文档.md:482-489）。
 * INT-927：后端 batch-action 已支持 move/copy/rename/modify-properties（INT-818，
 * 契约 api_gateway/schemas/audio.py BatchActionRequest），本卡移除「待 FEAT」禁用并透传
 * target_folder / rename_rule / property / property_value；SPL 为设备/API 级映射无 per-audio
 * 落点，后端明确拒绝（本期仅支持 metadata / audio-type），选择时禁用主钮并提示。
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
import {
  AUDIO_TYPE_OPTIONS,
  FOLDER_TARGET_OPTIONS,
  MODIFY_PROPERTY_OPTIONS,
} from '@/features/audio-import/constants'
import { useAudioMutations } from '@/application/audio/useAudioList'
import { ApiError } from '@/infrastructure/api/api-error'
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

/** 批量修改元数据的可改字段（对齐后端 _METADATA_PROPERTY_FIELDS：name/audio_type/asr_text/description/source_language） */
const METADATA_FIELD_OPTIONS = [
  { value: 'description', label: '描述' },
  { value: 'source_language', label: '源语言' },
  { value: 'asr_text', label: 'ASR 文本' },
  { value: 'name', label: '文件名' },
] as const

export function AudioBatchOperationDialog(props: AudioBatchOperationDialogProps) {
  const { batch } = useAudioMutations()
  const [targetFolder, setTargetFolder] = useState('test_data/dry')
  const [renameRule, setRenameRule] = useState('测试音频_')
  const [property, setProperty] = useState('metadata')
  const [metadataField, setMetadataField] = useState<string>('description')
  const [metadataValue, setMetadataValue] = useState('')
  const [audioTypeValue, setAudioTypeValue] = useState('dry')
  const [pending, setPending] = useState(false)

  const kind = props.state?.kind ?? null
  const bulkKind: BulkKind | null =
    kind === 'move' || kind === 'copy' || kind === 'rename' || kind === 'modify-properties'
      ? kind
      : null

  const showFolderTarget = bulkKind === 'move' || bulkKind === 'copy'
  const showRenameRule = bulkKind === 'rename'
  const showProperty = bulkKind === 'modify-properties'

  /** modify-properties 的属性值：metadata → 字段字典、audio-type → 类型值 */
  const propertyValue =
    property === 'audio-type'
      ? audioTypeValue
      : property === 'metadata'
        ? { [metadataField]: metadataValue }
        : undefined

  /** 主钮可用性：字段齐全且不触发后端明确拒绝的 SPL（无 per-audio 落点） */
  const canConfirm =
    bulkKind == null
      ? false
      : showFolderTarget
        ? targetFolder.trim() !== ''
        : showRenameRule
          ? renameRule.trim() !== ''
          : showProperty
            ? property !== 'spl' && (property !== 'metadata' || metadataValue.trim() !== '')
            : true

  const handleConfirm = async () => {
    if (!bulkKind) return
    setPending(true)
    try {
      const result = await batch.mutateAsync({
        action: bulkKind,
        ids: props.ids,
        targetFolder: showFolderTarget ? targetFolder : undefined,
        renameRule: showRenameRule ? renameRule : undefined,
        property: showProperty ? property : undefined,
        propertyValue: showProperty ? propertyValue : undefined,
      })
      toast.success(
        `批量操作完成：成功 ${result.successCount} 失败 ${result.total - result.successCount}`
      )
      props.onOpenChange(false)
    } catch (err) {
      // 透传后端校验文案（目标文件夹/重命名规则/属性名缺字段等 400）
      toast.error(err instanceof ApiError ? err.userMessage : '批量操作失败，请重试')
    } finally {
      setPending(false)
    }
  }

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
            <div className='space-y-3'>
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
              </div>

              {property === 'metadata' && (
                <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
                  <div className='space-y-2'>
                    <Label htmlFor='batch-meta-field'>元数据字段</Label>
                    <Select
                      value={metadataField}
                      onValueChange={(value) => setMetadataField(value ?? 'description')}
                    >
                      <SelectTrigger id='batch-meta-field' size='sm' className='w-full'>
                        <SelectValue placeholder='选择字段'>
                          {METADATA_FIELD_OPTIONS.find((o) => o.value === metadataField)?.label ?? ''}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {METADATA_FIELD_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='batch-meta-value'>值</Label>
                    <Input
                      id='batch-meta-value'
                      value={metadataValue}
                      onChange={(e) => setMetadataValue(e.target.value)}
                      placeholder='批量设置到选中音频'
                    />
                  </div>
                </div>
              )}

              {property === 'audio-type' && (
                <div className='space-y-2'>
                  <Label htmlFor='batch-audio-type-value'>音频类型</Label>
                  <Select
                    value={audioTypeValue}
                    onValueChange={(value) => setAudioTypeValue(value ?? 'dry')}
                  >
                    <SelectTrigger id='batch-audio-type-value' size='sm' className='w-full'>
                      <SelectValue placeholder='选择音频类型'>
                        {AUDIO_TYPE_OPTIONS.find((o) => o.value === audioTypeValue)?.label ?? ''}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {AUDIO_TYPE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {property === 'spl' && (
                <p className='text-muted-foreground text-xs'>
                  批量设置 SPL 暂不支持（SPL 为设备/API 级映射，audios 表无 per-audio 落点），本期仅支持元数据 / 音频类型
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' disabled={pending || !canConfirm} onClick={handleConfirm}>
            {pending ? '执行中...' : '确认执行'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
