/**
 * 音频试听配置弹窗（11_用例域.md §5.2，Dialog sm:max-w-md）。
 * 播放模式 RadioGroup「浏览器播放/实验室播放」+ 偏移量 Input（number 秒，默认 0）
 * + 主钮「开始试听」；载荷 POST /testcases/{id}/preview 携带 offset+preview_type（接线批次）。
 * 可视稿演示态：开始试听后 toast 演示。
 */
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
import { AudioPlayerPanel } from '@/features/testcases/modals/audio-player-dialog'
import type { TestCaseListItem } from '@/domain/models/testCase'

export function AudioPreviewConfigDialog({
  open,
  onOpenChange,
  caseItem,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseItem: TestCaseListItem | null
}) {
  const [mode, setMode] = useState<'frontend' | 'backend'>('frontend')
  const [offset, setOffset] = useState('0')
  /** 试听编排阶段：config=播放模式/偏移量配置；playing=音频播放器（§5.2） */
  const [stage, setStage] = useState<'config' | 'playing'>('config')

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) setStage('config')
      }}
    >
      <DialogContent className={stage === 'playing' ? 'sm:max-w-lg' : 'sm:max-w-md'}>
        <DialogHeader>
          <DialogTitle>
            {stage === 'playing' && caseItem
              ? `测试用例预览｜${caseItem.name} 音频`
              : '音频试听配置'}
          </DialogTitle>
          <DialogDescription>
            {stage === 'playing'
              ? '浏览器播放或实验室扬声器试听中'
              : caseItem
                ? `用例「${caseItem.name}」`
                : '预览所选用例的音频'}
          </DialogDescription>
        </DialogHeader>

        {stage === 'playing' ? (
          <AudioPlayerPanel
            mode={mode}
            caseItem={caseItem}
            onBack={() => setStage('config')}
          />
        ) : (
          <div className='space-y-4'>
            <div className='space-y-1.5'>
              <span className='text-sm font-medium'>播放模式</span>
              <div className='flex flex-col gap-1.5'>
                <label className='hover:bg-accent flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm'>
                  <input
                    type='radio'
                    name='preview-mode'
                    checked={mode === 'frontend'}
                    onChange={() => setMode('frontend')}
                  />
                  <span>
                    浏览器播放
                    <span className='text-muted-foreground block text-xs'>
                      音频将通过浏览器前端直接播放
                    </span>
                  </span>
                </label>
                <label className='hover:bg-accent flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm'>
                  <input
                    type='radio'
                    name='preview-mode'
                    checked={mode === 'backend'}
                    onChange={() => setMode('backend')}
                  />
                  <span>
                    实验室播放
                    <span className='text-muted-foreground block text-xs'>
                      音频将通过用例配置中的播放设备在实验室播放
                    </span>
                  </span>
                </label>
              </div>
            </div>
            <div className='flex items-center gap-2'>
              <span className='text-sm font-medium'>偏移量（秒）</span>
              <Input
                type='number'
                value={offset}
                onChange={(e) => setOffset(e.target.value)}
                className='h-8 w-32'
                aria-label='偏移量秒数'
              />
            </div>
          </div>
        )}

        {stage !== 'playing' && (
          <DialogFooter>
            <Button variant='outline' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button
              onClick={() => {
                toast.success('已开始试听（演示）')
                setStage('playing')
              }}
            >
              开始试听
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
