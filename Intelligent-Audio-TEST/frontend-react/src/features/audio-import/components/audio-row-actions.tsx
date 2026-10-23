/**
 * 音频行操作菜单（§5.3.1；DataTableRowActionMenu 对位，w-48 align='end'）。
 * 预览/详情/下载/转换格式/特征分析·质量评估/删除——按 audio:* 权限逐项显隐
 * （§8.3：algo_engineer 只读，仅预览/详情/下载/特征分析；删除 audio:delete、
 * 转换 audio:convert、编辑元数据 audio:update）。
 */
import {
  AudioLines,
  Download,
  Eye,
  MoreHorizontal,
  Pencil,
  Trash2,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { AudioAsset } from '@/domain/models/audio'

export type AudioRowActionsProps = {
  audio: AudioAsset
  canUpdate: boolean
  canConvert: boolean
  canDelete: boolean
  onPreview: () => void
  onMetadata: () => void
  onDownload: () => void
  onConvert: () => void
  onFeatureAnalysis: () => void
  onDelete: () => void
}

export function AudioRowActions(props: AudioRowActionsProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant='ghost'
            size='icon-sm'
            aria-label={`音频 ${props.audio.name} 的操作`}
          />
        }
      >
        <MoreHorizontal aria-hidden='true' />
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end' className='w-48'>
        <DropdownMenuItem onClick={props.onPreview}>
          <Eye aria-hidden='true' />
          预览
        </DropdownMenuItem>
        {props.canUpdate && (
          <DropdownMenuItem onClick={props.onMetadata}>
            <Pencil aria-hidden='true' />
            详情 / 编辑元数据
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onClick={props.onDownload}>
          <Download aria-hidden='true' />
          下载
        </DropdownMenuItem>
        {props.canConvert && (
          <DropdownMenuItem onClick={props.onConvert}>
            <AudioLines aria-hidden='true' />
            转换格式
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onClick={props.onFeatureAnalysis}>
          <AudioLines aria-hidden='true' />
          特征分析·质量评估
        </DropdownMenuItem>
        {props.canDelete && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant='destructive' onClick={props.onDelete}>
              <Trash2 aria-hidden='true' />
              删除
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
