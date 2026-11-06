/**
 * 文档变更卡（interfaces 层 ai-chat/message；08_AI对话页.md §3.4）：
 * studio_apply_edit / studio_restore_version 成功后消息内嵌——「文档已更新 · 版本 {n}」
 * + 增/删/改章节摘要 + 「查看文档」（切报告工作模式；待后端立项）。
 */
import { FilePenLine, History } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import type { ChatDocumentChange } from '@/domain/models/aiChat'

type DocumentChangeCardProps = {
  change: ChatDocumentChange
}

const ACTION_STYLES: Record<
  ChatDocumentChange['changes'][number]['action'],
  string
> = {
  新增: 'text-success',
  删除: 'text-destructive',
  修改: 'text-foreground',
}

export function DocumentChangeCard({ change }: DocumentChangeCardProps) {
  const handleViewDocument = () => {
    toast.info('报告工作模式待后端立项', {
      description: '文档预览与 Studio 版本能力随后端立项整体放开。',
    })
  }

  return (
    <div className='border-border/70 bg-background/60 not-prose mb-4 w-full rounded-md border p-3'>
      <div className='flex items-center gap-2'>
        <FilePenLine className='text-primary size-4' />
        <span className='text-sm font-medium'>
          文档已更新 · 版本 {change.version}
        </span>
        <Button
          className='text-primary h-6 px-2 text-xs'
          onClick={handleViewDocument}
          size='sm'
          type='button'
          variant='ghost'
        >
          查看文档
        </Button>
      </div>
      <ul className='text-muted-foreground mt-2 space-y-1 text-xs leading-5'>
        {change.changes.map((item, index) => (
          <li className='flex items-center gap-1.5' key={index}>
            <span className={`font-medium ${ACTION_STYLES[item.action]}`}>
              {item.action}
            </span>
            <span>{item.section}</span>
          </li>
        ))}
      </ul>
      <div className='text-muted-foreground mt-2 flex items-center gap-1.5 text-[11px]'>
        <History className='size-3' />
        恢复历史版本将产生新版本，不覆盖当前文档
      </div>
    </div>
  )
}
