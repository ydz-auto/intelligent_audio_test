/**
 * 报告工作模式·文档预览栏（interfaces 层 ai-chat/studio；08_AI对话页.md §3.6）。
 * 双栏增强态右栏：头行（文档名 + 版本 Badge + 历史版本/导出/编辑/关闭）+ Markdown 预览
 * （Response 复用）+ 底部提示「AI 只起草不算数」。
 * Agent 后端立项前整块隐藏（入口钮不渲染），本文件仅供骨架与后续接线引用。
 */
import { Download, FileText, History, PenLine, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Response } from '@/components/ai-elements/response'

type DocumentPanelProps = {
  documentName: string
  version: number
  content: string
  onClose: () => void
}

export function DocumentPanel({
  documentName,
  version,
  content,
  onClose,
}: DocumentPanelProps) {
  return (
    <div className='border-border/60 bg-background/60 dark:bg-background/40 flex min-h-0 flex-col border-l'>
      <div className='border-b px-4 py-2.5'>
        <div className='flex items-center gap-2'>
          <FileText className='text-muted-foreground size-4' />
          <span className='min-w-0 truncate text-sm font-semibold'>
            文档预览
          </span>
          <span className='min-w-0 truncate text-xs'>{documentName}</span>
          <Badge className='shrink-0' variant='outline'>
            版本 {version}
          </Badge>
          <div className='ml-auto flex items-center gap-0.5'>
            <Button
              className='text-muted-foreground size-7'
              size='icon'
              type='button'
              variant='ghost'
              aria-label='历史版本'
            >
              <History className='size-4' />
            </Button>
            <Button
              className='text-muted-foreground size-7'
              size='icon'
              type='button'
              variant='ghost'
              aria-label='导出'
            >
              <Download className='size-4' />
            </Button>
            <Button
              className='text-muted-foreground size-7'
              size='icon'
              type='button'
              variant='ghost'
              aria-label='编辑文档'
            >
              <PenLine className='size-4' />
            </Button>
            <Button
              className='text-muted-foreground size-7'
              onClick={onClose}
              size='icon'
              type='button'
              variant='ghost'
              aria-label='关闭'
            >
              <X className='size-4' />
            </Button>
          </div>
        </div>
      </div>
      <div className='min-h-0 flex-1 overflow-y-auto px-5 py-4'>
        <Response>{content}</Response>
      </div>
      <div className='border-t px-4 py-2 text-xs text-muted-foreground'>
        [Demo] AI 只起草不算数：文档数值全部来自报告七表；每次修改自动保存版本快照。
      </div>
    </div>
  )
}
