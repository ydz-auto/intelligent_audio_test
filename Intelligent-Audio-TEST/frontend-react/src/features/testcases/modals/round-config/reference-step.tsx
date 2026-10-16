/**
 * 轮次步骤⑤：参考参数（11_用例域.md §5.1）。
 * 路径行（FolderOpen 图标 + referenceParamsPath）+「查看/编辑」切换钮；
 * 未生成时空态「参考参数将在音频关联后自动生成」；编辑态 Textarea mono + 「保存」。
 */
import { Eye, FolderOpen, Pencil, Save } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

export function ReferenceStep({ generated = false }: { generated?: boolean }) {
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const [content, setContent] = useState('')

  if (!generated) {
    return (
      <div className='flex items-center gap-3 rounded-lg border border-dashed p-4'>
        <FolderOpen aria-hidden='true' className='text-muted-foreground size-5 shrink-0' />
        <p className='text-muted-foreground text-sm'>
          参考参数将在音频关联后自动生成——当前轮次尚未生成参考参数。
        </p>
      </div>
    )
  }

  return (
    <div className='space-y-3'>
      <div className='bg-background ring-foreground/10 flex items-center gap-3 rounded-lg p-3 ring-1'>
        <FolderOpen aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
        <code className='text-muted-foreground min-w-0 flex-1 truncate text-xs'>
          /data/ref_params/tc-001/round_1/params.json
        </code>
        <Button
          type='button'
          variant='ghost'
          size='sm'
          className='h-7 gap-1'
          onClick={() => setMode(mode === 'view' ? 'edit' : 'view')}
        >
          {mode === 'view' ? (
            <>
              <Pencil aria-hidden='true' className='size-3.5' />
              查看/编辑
            </>
          ) : (
            <>
              <Eye aria-hidden='true' className='size-3.5' />
              返回查看
            </>
          )}
        </Button>
      </div>
      {mode === 'edit' && (
        <div className='space-y-2'>
          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={5}
            className='font-mono text-xs'
            placeholder='编辑参考参数 JSON…'
          />
          <div className='flex justify-end gap-2'>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='h-7'
              onClick={() => setMode('view')}
            >
              取消
            </Button>
            <Button
              type='button'
              size='sm'
              className='h-7 gap-1'
              onClick={() => {
                toast.success('参考参数已保存')
                setMode('view')
              }}
            >
              <Save aria-hidden='true' className='size-3.5' />
              保存
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
